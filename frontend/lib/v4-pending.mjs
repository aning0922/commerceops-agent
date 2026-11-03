const operations = new Set(['session_create', 'persona', 'reset', 'logout']);
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
// Failure to read a previous request must never be interpreted as no request.
export function readPending(storage, slot) {
  try {
    const raw = storage.getItem(slot);
    if (raw === null) return null;
    const value = JSON.parse(raw);
    if (!value || typeof value !== 'object' || Array.isArray(value) ||
        Object.keys(value).length !== 2 || !operations.has(value.operation) ||
        typeof value.key !== 'string' || !uuid.test(value.key)) {
      return {operation: 'storage_unavailable', key: ''};
    }
    return {operation: value.operation, key: value.key};
  } catch {
    return {operation: 'storage_unavailable', key: ''};
  }
}
