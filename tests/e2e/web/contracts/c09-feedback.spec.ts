import { test, expect } from "../../../../frontend/tooling/web-test";
import { statusView } from "../../../../frontend/lib/p3-present";
import { P3Failure } from "../../../../frontend/lib/p3-transport";

test("C09 中文与原枚举状态共用语义；已记录意见不改为执行完成", () => {
  expect(statusView("completed")).toEqual(statusView("已完成"));
  expect(statusView("failed")).toEqual(statusView("失败"));
  expect(statusView("open")).toEqual({
    text: "待跟进",
    tone: "warning",
    known: true,
  });
  expect(statusView("needs_reapproval").text).toBe("需要重新审批");
  expect(statusView("approved").text).toBe("批准已记录");
  expect(statusView("unknown").tone).toBe("warning");
  expect(statusView("sync_failed").tone).toBe("danger");
  expect(statusView("未来状态")).toEqual({
    text: "状态未识别",
    tone: "neutral",
    known: false,
  });
});
test("C09 未知/冲突/过期/换版反馈分开，不给出新键自动重试指令", () => {
  expect(new P3Failure("WRITE_RESULT_UNKNOWN").message).toContain("原请求");
  expect(new P3Failure("IDEMPOTENCY_CONFLICT").message).toContain("原回执");
  expect(new P3Failure("PLAN_CHANGED").message).toContain("旧意见不授权新版本");
  expect(new P3Failure("SESSION_INVALID").message).toContain("重新登录");
  expect(new P3Failure("ITEM_VERSION_CONFLICT").message).toContain(
    "不会自动换键",
  );
});
