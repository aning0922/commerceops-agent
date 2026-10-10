import "server-only";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { MockRole, MockView, SkuFact, FixtureState } from "./view-model";
// Explicit server process fixtures only. No query/cookie/header can assign a role.
// No production auth, session, receipt or server permission is simulated by this source.
export function mockView(version?: string): MockView {
  const enabled = process.env.COMMERCEOPS_UI_MODE === "mock";
  const roleValue = process.env.COMMERCEOPS_MOCK_ROLE;
  const role: MockRole =
    enabled && ["operator", "approver", "admin"].includes(roleValue ?? "")
      ? (roleValue as MockRole)
      : "unauthorized";
  const stateValue = process.env.COMMERCEOPS_MOCK_STATE ?? "ready";
  const states: FixtureState[] = [
    "ready",
    "loading",
    "empty",
    "error",
    "expired",
    "revoked",
    "duplicate",
    "conflict",
    "unknown",
  ];
  const state = states.includes(stateValue as FixtureState)
    ? (stateValue as FixtureState)
    : "error";
  const businessRead =
    enabled &&
    ["operator", "approver"].includes(role) &&
    state !== "expired" &&
    state !== "revoked";
  const proofId = enabled ? process.env.COMMERCEOPS_MOCK_PROOF_ID : undefined;
  let proof: MockView["proof"] = null;
  if (proofId) {
    try {
      proof = {
        serviceId: proofId,
        buildId: readFileSync(
          join(process.cwd(), ".next", "BUILD_ID"),
          "utf8",
        ).trim(),
      };
    } catch {
      /* Missing build identity fails proof closed. */
    }
  }
  const base: MockView = {
    proof,
    mode: enabled ? "mock" : "unavailable",
    role,
    state,
    name:
      role === "approver" ? "陈审批" : role === "admin" ? "陈管理" : "林运营",
    home:
      role === "admin"
        ? "/admin/operations"
        : businessRead
          ? "/tasks"
          : "/access",
    businessRead,
    canDraft: businessRead && role === "operator",
    canDecide: businessRead && role === "approver",
    canResolve: businessRead && role === "approver",
    adminRead:
      enabled && role === "admin" && state !== "expired" && state !== "revoked",
    tasks: [],
    items: [],
    facts: [],
    completedFacts: [],
    historyAvailable: true,
    planKeys: [],
    taskId: "INV-DEMO-008",
    approvalId: "APR-DEMO-008",
    reportId: "REPORT-DEMO-008",
    snapshotId: "DEMO-SNAPSHOT-008",
    version: version === "1" ? 1 : 2,
    historical: version === "1",
    taskStatus: "awaiting_approval",
    expiresAt: null,
    freshness: null,
  };
  if (!businessRead) return base;
  const facts: SkuFact[] = [
    {
      key: "SKU-A",
      name: "轻量帆布袋 · 原色",
      demand: 70,
      inventory: 20,
      inbound: 0,
      suggested: 100,
      risk: "补货风险",
      explanation: "可进入审批 · 在途已知",
    },
    {
      key: "SKU-B",
      name: "基础棉 T 恤 · 雾蓝 / M",
      demand: 42,
      inventory: 0,
      inbound: null,
      suggested: 72,
      risk: "缺货",
      explanation: "草案 · 在途未知按 0 估算，可能重复补货",
    },
    {
      key: "SKU-C",
      name: "陶瓷咖啡杯 · 350mL",
      demand: 14,
      inventory: -3,
      inbound: 4,
      suggested: 23,
      risk: "缺货",
      explanation: "可进入审批 · 保留负库存",
    },
    {
      key: "SKU-D",
      name: "桌面收纳盒 · 灰",
      demand: 35,
      inventory: 120,
      inbound: 0,
      suggested: 0,
      risk: "正常",
      explanation: "无需自动补货",
    },
    {
      key: "SKU-E",
      name: "贴纸组合 · 6 枚",
      demand: 0,
      inventory: 18,
      inbound: 0,
      suggested: 0,
      risk: "无近期需求",
      explanation: "不推导数量",
    },
    {
      key: "SKU-F",
      name: "旅行收纳包 · 黑",
      demand: 28,
      inventory: null,
      inbound: null,
      suggested: null,
      risk: "无法判定",
      explanation: "硬阻断 · 库存未知，不可执行",
    },
  ];
  // Task007 has its own fixed two-SKU source, independent of task008 capacity variant.
  base.completedFacts = facts.slice(0, 2).map((x) => ({ ...x }));
  if (process.env.COMMERCEOPS_MOCK_CAPACITY === "20") {
    // Fixed, fully disclosed capacity fixture; no business Q calculation in the UI.
    facts.splice(
      0,
      facts.length,
      ...Array.from({ length: 20 }, (_, i): SkuFact => ({
        key: `SKU-${String(i + 1).padStart(2, "0")}`,
        name: `长中文商品名称与规格完整披露样例 · 第 ${i + 1} 项 · 雾蓝色 / 加大尺寸`,
        demand: 42,
        inventory: 0,
        inbound: i === 0 || i === 19 ? null : 0,
        suggested: 72,
        risk: "缺货",
        explanation:
          i === 0 || i === 19
            ? "草案 · 在途未知按 0 估算，可能重复补货"
            : "可进入审批 · 在途已知",
      })),
    );
  }
  base.facts = facts;
  base.planKeys = facts
    .filter((x) => x.suggested !== null && x.suggested > 0)
    .map((x) => x.key);
  base.tasks = [
    {
      id: base.taskId,
      title: "近 7 天销量与库存分析",
      status: "awaiting_approval",
      updated: "16:30",
      scope: "全部商品",
    },
    {
      id: "INV-DEMO-007",
      title: "库存风险复查",
      status: "completed",
      updated: "15:48",
      scope: "SKU-A / SKU-B",
    },
    {
      id: "INV-DEMO-006",
      title: "核心商品补货建议",
      status: "analyzing",
      updated: "15:42",
      scope: "12 个 SKU",
    },
    {
      id: "INV-DEMO-005",
      title: "近 7 天商品库存检查",
      status: "queued",
      updated: "15:40",
      scope: "全部商品",
    },
  ];
  base.items = [
    {
      sourceTaskId: "INV-DEMO-008",
      sourceReportVersion: 1,
      id: "RI-DEMO-001",
      sku: "SKU-A",
      name: "轻量帆布袋 · 原色",
      quantity: 100,
      status: "open",
      version: 1,
      sync: "sync_pending",
      reason: null,
    },
    {
      sourceTaskId: "INV-DEMO-008",
      sourceReportVersion: 1,
      id: "RI-DEMO-002",
      sku: "SKU-B",
      name: "基础棉 T 恤 · 雾蓝 / M",
      quantity: 72,
      status: "open",
      version: 1,
      sync: "sync_failed",
      reason: null,
    },
    {
      sourceTaskId: "INV-DEMO-008",
      sourceReportVersion: 1,
      id: "RI-DEMO-003",
      sku: "SKU-C",
      name: "陶瓷咖啡杯 · 350mL",
      quantity: 23,
      status: "completed",
      version: 2,
      sync: "sync_unknown",
      reason: "已记录内部跟进结果（Mock）",
    },
  ];
  return base;
}
