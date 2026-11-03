import { test, expect } from "@playwright/test";
import { BoundedNetwork } from "../m3-live/bounded-network";
const web = "http://127.0.0.1:8888", api = "http://127.0.0.1:9999";
test("exact path, query, body and one-shot limit are enforced before continue", () => {
 const guard = new BoundedNetwork(web, api, 1000, 100);
 guard.allow({ method: "POST", pathname: "/api/v1/daily-reports", search: "", remaining: 1, body: x => x === '{"shop_id":"owned"}' });
 expect(guard.accept({ url: api + "/api/v1/daily-reports", method: "POST", body: "{}" }, 1)).toBe(false);
 expect(guard.accept({ url: api + "/api/v1/daily-reports?x=1", method: "POST", body: '{"shop_id":"owned"}' }, 1)).toBe(false);
 expect(guard.accept({ url: web + "/api/v1/daily-reports", method: "POST", body: '{"shop_id":"owned"}' }, 1)).toBe(false);
 expect(guard.accept({ url: api + "/api/v1/daily-reports", method: "POST", body: '{"shop_id":"owned"}' }, 1)).toBe(true);
 expect(guard.accept({ url: api + "/api/v1/daily-reports", method: "POST", body: '{"shop_id":"owned"}' }, 1)).toBe(false);
});
test("unknown API, credentials, cross-origin and deadline fail closed", () => {
 const g = new BoundedNetwork(web, api, 1000, 100); g.allow({ method: "GET", pathname: "/api/v1/auth/session", search: "", remaining: 2 });
 expect(g.accept({ url: api + "/api/v1/auth/session", method: "GET", body: null }, 899)).toBe(true);
 expect(g.accept({ url: api + "/api/v1/auth/session", method: "GET", body: null }, 900)).toBe(false);
 expect(g.accept({ url: api + "/api/v1/copy/candidates", method: "GET", body: null }, 1)).toBe(false);
 expect(g.accept({ url: "http://evil:pass@127.0.0.1:9999/api/v1/auth/session", method: "GET", body: null }, 1)).toBe(false);
 expect(g.accept({ url: "https://evil.example/_next/static/a.js", method: "GET", body: null }, 1)).toBe(false);
});
test("one generated Copy capability probe is bounded to its exact endpoint", () => {
 const g = new BoundedNetwork(web, api, 1000, 100); g.allowCopyProbe();
 const id = "00000000-0000-0000-0000-000000000001";
 expect(g.accept({url: api + "/api/v1/copy/candidates/" + id,method:"GET",body:null}, 1)).toBe(false);
 expect(g.accept({url: api + "/api/v1/copy/candidate-requests/" + id,method:"GET",body:null}, 1)).toBe(true);
 expect(g.accept({url: api + "/api/v1/copy/candidate-requests/" + id,method:"GET",body:null}, 1)).toBe(false);
});
test("loss injection forwards once, disables retry/redirect and aborts the actual response", async () => {
 const { dropActualResponse } = await import("../m3-live/drop-response");
 const calls: string[] = [];
 const status = await dropActualResponse({ fetch: async opts => { calls.push(JSON.stringify(opts)); return { status: () => 202 }; }, abort: async code => { calls.push(code); } }, 2500);
 expect(status).toBe(202); expect(calls).toEqual(['{"maxRetries":0,"maxRedirects":0,"timeout":2500}', "failed"]);
});
test("loss injection still aborts when the real forward fails", async () => {
 const { dropActualResponse } = await import("../m3-live/drop-response"); let count = 0;
 await expect(dropActualResponse({ fetch: async () => { throw new Error("network"); }, abort: async () => { count++; } }, 100)).rejects.toThrow("network"); expect(count).toBe(1);
});
test("framework navigation permits only the authorized home and bounded RSC query", () => {
 const g = new BoundedNetwork(web, api, 1000, 100); g.allowRsc("/tasks", 1);
 expect(g.accept({url:web + "/tasks?_rsc=a1",method:"GET",body:null},1)).toBe(true);
 expect(g.accept({url:web + "/tasks?_rsc=a2",method:"GET",body:null},1)).toBe(false);
 expect(g.accept({url:web + "/api/v1/tasks?_rsc=a1",method:"GET",body:null},1)).toBe(false);
});
