// Context is server-derived. This helper only prevents stale rendering; it is not authorization.
export function createContextGate() {
  let generation = 0;
  let context = null;
  let shop = null;
  let sequence = 0;
  return {
    invalidate() { generation++; context = null; shop = null; sequence++; },
    establish(value) {
      generation++; sequence++; shop = null;
      context = value && value.shop_id === null ? { ...value } : null;
    },
    selectShop(id) { generation++; sequence++; shop = id; },
    begin() {
      if (!context) return null;
      return { generation, sequence: ++sequence, context: { ...context }, shop };
    },
    accepts(ticket, response) {
      if (!ticket || !context || !response || ticket.generation !== generation || ticket.sequence !== sequence) return false;
      const a = ticket.context;
      return ['tenant_id', 'organization_id', 'principal_id', 'reset_epoch', 'auth_generation'].every(k => a[k] === context[k] && a[k] === response[k]) && response.shop_id === ticket.shop && shop === ticket.shop;
    },
  };
}
