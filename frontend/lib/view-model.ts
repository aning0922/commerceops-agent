// UI-only offline fixture model. This is not the service DTO or API contract.
export type MockRole = "operator" | "approver" | "admin" | "unauthorized";
export type FixtureState =
  | "ready"
  | "loading"
  | "empty"
  | "error"
  | "expired"
  | "revoked"
  | "duplicate"
  | "conflict"
  | "unknown";
export type SkuFact = {
  key: string;
  name: string;
  demand: number;
  inventory: number | null;
  inbound: number | null;
  suggested: number | null;
  risk: string;
  explanation: string;
};
export type TaskFact = {
  id: string;
  title: string;
  status: string;
  updated: string;
  scope: string;
};
export type ItemFact = {
  id: string;
  sku: string;
  name: string;
  quantity: number;
  status: "open" | "completed" | "closed";
  version: number;
  sync: string;
  reason: string | null;
};
export type MockView = {
  mode: "mock" | "unavailable";
  role: MockRole;
  state: FixtureState;
  name: string;
  home: string;
  businessRead: boolean;
  canDraft: boolean;
  canDecide: boolean;
  canResolve: boolean;
  adminRead: boolean;
  tasks: TaskFact[];
  items: ItemFact[];
  facts: SkuFact[];
  planKeys: string[];
  taskId: string;
  approvalId: string;
  reportId: string;
  snapshotId: string;
  version: number;
  historical: boolean;
  taskStatus: string;
  expiresAt: string | null;
  freshness: string | null;
};
