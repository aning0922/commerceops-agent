import {isSessionContext} from './v4-context.mjs';
const operations = new Set(['session_create', 'persona', 'reset', 'logout']);
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
// Failure to read a previous request must never be interpreted as no request.
export function readPending(storage, slot) {
  try {
    const raw = storage.getItem(slot);
    if (raw === null) return null;
    const value = JSON.parse(raw);
    if (!value || typeof value !== 'object' || Array.isArray(value) ||
        ![2,3].includes(Object.keys(value).length) || !operations.has(value.operation) ||
        typeof value.key !== 'string' || !uuid.test(value.key)) {
      return {operation: 'storage_unavailable', key: ''};
    }
    if (Object.keys(value).length === 2) return {operation: value.operation, key: value.key};
    const proof=value.proof;
    if (value.operation === 'session_create' || !proof || typeof proof !== 'object' || Array.isArray(proof) ||
        Object.keys(proof).length !== 4 || !isSessionContext(proof.context) ||
        typeof proof.creation_request_key !== 'string' || !uuid.test(proof.creation_request_key) ||
        typeof proof.persona_id !== 'string' || !proof.persona_id || proof.persona_id.length > 80 ||
        (value.operation === 'persona' ? typeof proof.target_persona !== 'string' || !proof.target_persona || proof.target_persona.length > 80 : proof.target_persona !== null)) {
      return {operation: 'storage_unavailable', key: ''};
    }
    return {operation: value.operation, key: value.key, proof};
  } catch {
    return {operation: 'storage_unavailable', key: ''};
  }
}
