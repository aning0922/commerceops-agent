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
