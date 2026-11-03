import Ajv2020 from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';

// Mirrors the frozen Context DTO. This prevents stale rendering, not authorization.
const ajv = new Ajv2020({strict: true});
addFormats(ajv);
const validContext = ajv.compile({
  type: 'object', additionalProperties: false,
  properties: {
    tenant_id: {type: 'string', format: 'uuid'},
    organization_id: {type: 'string', format: 'uuid'},
    principal_id: {type: 'string', format: 'uuid'},
    shop_id: {anyOf: [{type: 'string', format: 'uuid'}, {type: 'null'}]},
    reset_epoch: {type: 'integer', minimum: 0},
    auth_generation: {type: 'integer', minimum: 0},
    authorized_at: {type: 'string', format: 'date-time'},
  },
  required: ['tenant_id', 'organization_id', 'principal_id', 'shop_id', 'reset_epoch', 'auth_generation', 'authorized_at'],
});
const validShop = ajv.compile({anyOf: [{type: 'string', format: 'uuid'}, {type: 'null'}]});
const validUuid = ajv.compile({type: 'string', format: 'uuid'});
export function isSessionContext(value) {
  return validContext(value) && value.shop_id === null &&
    Number.isSafeInteger(value.reset_epoch) && Number.isSafeInteger(value.auth_generation);
}
// Session and shop responses have different shop_id values; compare the remaining identity boundary.
export function sameIdentityContext(left, right) {
  if (!validContext(left) || !validContext(right)) return false;
  return left.tenant_id === right.tenant_id &&
    left.organization_id === right.organization_id &&
    left.principal_id === right.principal_id &&
    left.reset_epoch === right.reset_epoch &&
    left.auth_generation === right.auth_generation;
}
export function createContextGate() {
  let generation = 0;
  let context = null;
  let shop = null;
  let sequence = 0;
  return {
    invalidate() { generation++; context = null; shop = null; sequence++; },
    establish(value) {
      generation++; sequence++; shop = null;
      context = validContext(value) && value.shop_id === null ? { ...value } : null;
    },
    selectShop(id) { generation++; sequence++; shop = validShop(id) ? id : null; if (!validShop(id)) context = null; },
    begin() {
      if (!context || !validContext(context)) return null;
      return { generation, sequence: ++sequence, context: { ...context }, shop };
    },
    accepts(ticket, response) {
      if (!ticket || !context || !validContext(context) || !validContext(ticket.context) || !validContext(response) || !validShop(ticket.shop) || ticket.generation !== generation || ticket.sequence !== sequence) return false;
      const a = ticket.context;
      return ['tenant_id', 'organization_id', 'principal_id', 'reset_epoch', 'auth_generation'].every(k => a[k] === context[k] && a[k] === response[k]) && response.shop_id === ticket.shop && shop === ticket.shop;
    },
  };
}

// The HTTP schema validates the complete receipt; this additionally binds it to the request's tenant and returned context.
export function matchesControlBoundary(before, result, operation, requestKey) {
  if (!validContext(before) || before.shop_id !== null || !result ||
      !validContext(result.context) || result.context.shop_id !== null) return false;
  const after = result.context;
  const receipt = result.data?.receipt;
  if (!receipt || !['OK', 'COMMITTED'].includes(result.status) ||
      receipt.status !== 'COMMITTED' || receipt.operation !== operation ||
      receipt.request_key !== requestKey || after.tenant_id !== before.tenant_id ||
      after.organization_id !== before.organization_id ||
      receipt.reset_epoch !== after.reset_epoch ||
      receipt.auth_generation !== after.auth_generation ||
      !Number.isSafeInteger(before.reset_epoch) || !Number.isSafeInteger(before.auth_generation) ||
      !Number.isSafeInteger(after.reset_epoch) || !Number.isSafeInteger(after.auth_generation)) return false;
  if (operation === 'logout') {
    return result.data.next_step === 'LOGGED_OUT' &&
      after.principal_id === before.principal_id &&
      after.reset_epoch === before.reset_epoch &&
      after.auth_generation === before.auth_generation;
  }
  if (operation === 'reset') {
    return result.data.next_step === 'READ_CURRENT_SESSION' &&
      after.principal_id === before.principal_id &&
      after.reset_epoch === before.reset_epoch + 1 &&
      after.auth_generation === before.auth_generation + 1;
  }
  if (operation === 'persona') {
    return result.data.next_step === 'READ_CURRENT_SESSION' &&
      after.reset_epoch === before.reset_epoch &&
      after.auth_generation === before.auth_generation + 1;
  }
  return false;
}

export function matchesControlReadback(beforeSession, result, current, operation, targetPersona) {
  if (!beforeSession || !current || !validUuid(beforeSession.data?.creation_request_key) ||
      typeof beforeSession.data?.persona_id !== 'string' || !beforeSession.data.persona_id ||
      !sameIdentityContext(result?.context, current.context) || current.context.shop_id !== null ||
      current.data?.creation_request_key !== beforeSession.data?.creation_request_key) return false;
  if (operation === 'reset') return current.data?.persona_id === beforeSession.data?.persona_id;
  if (operation === 'persona') return typeof targetPersona === 'string' && targetPersona.length > 0 && current.data?.persona_id === targetPersona;
  return false;
}

export function matchesCreateBoundary(result, current, requestKey) {
  if (!result || !current || !['OK', 'COMMITTED'].includes(result.status) ||
      !validContext(result.context) || result.context.shop_id !== null ||
      !validContext(current.context) || current.context.shop_id !== null ||
      !sameIdentityContext(result.context, current.context)) return false;
  const receipt = result.data?.receipt;
  return receipt?.status === 'COMMITTED' && receipt.operation === 'session_create' &&
    receipt.request_key === requestKey && receipt.reset_epoch === result.context.reset_epoch &&
    receipt.auth_generation === result.context.auth_generation &&
    result.data?.session?.creation_request_key === requestKey &&
    current.data?.creation_request_key === requestKey;
}

// Recovery can establish the effect only when the original non-secret pre-operation proof is available.
export function matchesRecoveredControl(proof, receipt, current, operation, requestKey) {
  if (!proof || !current || !receipt || !['reset','persona'].includes(operation)) return false;
  const beforeSession = {context: proof.context, data: {creation_request_key: proof.creation_request_key, persona_id: proof.persona_id}};
  const result = {status:'COMMITTED', context:current.context, data:{receipt,next_step:'READ_CURRENT_SESSION'}};
  return matchesControlBoundary(proof.context,result,operation,requestKey) &&
    matchesControlReadback(beforeSession,result,current,operation,proof.target_persona);
}

// Late read failures may invalidate the still-current identity, but must not erase a newer identity or shop selection.
export function shouldClearSummaryFailure(base, current, selectedShop, requestShop) {
  return !!current && selectedShop === requestShop &&
    typeof requestShop === 'string' && requestShop.length > 0 &&
    sameIdentityContext(base, current);
}
