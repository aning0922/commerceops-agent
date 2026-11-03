import { test, expect } from "@playwright/test";
import { copyApi, mayReview, validCandidate, validCreate, validReview } from "../lib/p6-copy-client";
import type { CreateCopy, ReviewCopy } from "../lib/p6-copy-client";
import fixture from "./copy.fixture.json" with { type: "json" };
const c = fixture.pending.data.candidate;
const create: CreateCopy = { schema_version: "p6-copy-web-v1", shop_id: c.retrieval.scope.shop_id, registry_id: c.retrieval.registry_id, registry_digest: c.retrieval.registry_digest, product_source_id: c.product_source_id, query_ref: "demo@v1", reviewer_id: c.reviewer_id, request_key: "00000000-0000-0000-0000-000000000001" };
const review: ReviewCopy = { schema_version: "p6-copy-web-v1", candidate_version: "v1", candidate_hash: c.candidate_hash, request_key: fixture.decision_saved.data.request_key, action: "approve", reason: "核对来源" };
const json = (x: unknown, status = 200) => new Response(JSON.stringify(x), { status, headers: { "content-type": "application/json" } });
test("frozen DTO fixture enforces template, cited text and closed states", () => {
 expect(validCandidate(fixture.pending)).toBe(true); expect(validCreate(create)).toBe(true); expect(validReview(review)).toBe(true);
 if (!validCandidate(fixture.pending)) throw new Error("fixture invalid");
 expect(mayReview(fixture.pending.data, c.reviewer_id, [c.retrieval.scope.shop_id])).toBe(true);
 expect(mayReview(fixture.pending.data, c.owner_id, [])).toBe(false);
 expect(mayReview(fixture.pending.data, "00000000-0000-0000-0000-000000000003", [c.retrieval.scope.shop_id])).toBe(false);
 const changed = structuredClone(fixture.pending); changed.data.candidate.text += "额外断言"; expect(validCandidate(changed)).toBe(false);
 const flag = structuredClone(fixture.pending); (flag.data as Record<string, unknown>).publication_allowed = 0; expect(validCandidate(flag)).toBe(false);
});
test("creation unknown stays on original key GET; probe verifies actual UNKNOWN", async () => {
 const paths: string[] = []; let known = false;
 const api = copyApi({ origin: new URL("http://localhost:9000"), csrf: () => "token", current: () => true, invalidate: () => {}, transport: async (url, init) => { paths.push(`${init.method} ${url.pathname}`); if (init.method === "POST") throw Error("lost"); return known ? json(fixture.pending) : json({schema_version:"p6-copy-web-v1",data:{state:"UNKNOWN",request_key:create.request_key,publication_allowed:false}},202); } });
 expect(await api.probe(create.request_key)).toBe(true); await expect(api.create(create)).rejects.toMatchObject({ code: "UNKNOWN" }); await expect(api.create(create)).rejects.toMatchObject({ code: "UNKNOWN" });
 expect(await api.candidateReceipt(create)).toBe(null); known = true; expect((await api.candidateReceipt(create))?.candidate.candidate_id).toBe(c.candidate_id);
 expect(paths.filter(x => x.startsWith("POST")).length).toBe(1);
});
test("review receipt checks original key, candidate, hash and action", async () => {
 let value: unknown = fixture.decision_saved;
 const api = copyApi({ origin: new URL("http://localhost:9000"), csrf: () => "token", current: () => true, invalidate: () => {}, transport: async url => { expect(url.searchParams.get("candidate_hash")).toBe(c.candidate_hash); return json(value); } });
 expect((await api.reviewReceipt(c.candidate_id, review)).state).toBe("saved");
 value = { ...fixture.decision_saved, data: { ...fixture.decision_saved.data, candidate_hash: "f".repeat(64) } }; await expect(api.reviewReceipt(c.candidate_id, review)).rejects.toMatchObject({ code: "INVALID" });
 value = fixture.decision_rejected; await expect(api.reviewReceipt(c.candidate_id, review)).rejects.toMatchObject({ code: "INVALID" });
});
test("stale copy 403 cannot invalidate replacement session", async () => {
 let current = true, cleared = 0, finish!: (r: Response) => void;
 const api = copyApi({ origin: new URL("http://localhost:9000"), csrf: () => "token", current: () => current, invalidate: () => cleared++, transport: () => new Promise(resolve => { finish = resolve; }) });
 const pending = api.read(c.candidate_id); current = false; finish(json({},403)); await expect(pending).rejects.toMatchObject({ code: "STALE" }); expect(cleared).toBe(0);
});
test("review UNKNOWN is never resubmitted and recovers by original key", async () => {
 const methods: string[] = []; let final = false;
 const api = copyApi({ origin: new URL("http://localhost:9000"), csrf: () => "token", current: () => true, invalidate: () => {}, transport: async (_url, init) => { methods.push(String(init.method)); return init.method === "POST" || !final ? json(fixture.decision_UNKNOWN,202) : json(fixture.decision_saved); } });
 await api.review(c.candidate_id, review); await expect(api.review(c.candidate_id, review)).rejects.toMatchObject({ code: "UNKNOWN" });
 expect((await api.reviewReceipt(c.candidate_id, review)).state).toBe("UNKNOWN"); final = true;
 expect((await api.reviewReceipt(c.candidate_id, review)).state).toBe("saved"); expect(methods).toEqual(["POST", "GET", "GET"]);
});
