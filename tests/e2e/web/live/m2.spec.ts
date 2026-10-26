import { test } from "../../../../frontend/tooling/web-test";
import { runM2 } from "./m2-consumer";
// Both cases are registered; A's frozen --grep selects exactly one. Phase mismatch fails pre-login.
test("M2 source", async ({ browser }, info) => { await runM2(browser, info, "source_ready"); });
test("M2 restored", async ({ browser }, info) => { await runM2(browser, info, "restored_pending_verified"); });
