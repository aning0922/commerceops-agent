# M3 inquiry shared application wiring candidate

2026-11-03. `IMPLEMENTATION_CANDIDATE / INDEPENDENT_REVIEW_PENDING / INTEGRATED_PG_NOT_RUN`.
Parent snapshot: `8b5000e276a0193bcbcb00ead418c6e1226e7a71`, containing frozen S3
`32dd7c2` and inquiry `e2e50f5`; their SQL findings remain separately recorded.

The API and existing single Worker accept one explicit
`COMMERCEOPS_M3_INQUIRY_CONFIG_FILE`. The bounded private-file loader accepts only
`p6-inquiry-deployment-v1`, an internal shop UUID, an absolute fixture directory,
the baseline Mock case, and an explicit boolean enable switch (default false).
Mode is fixed `offline_stub`; actual model requests and external sending are
literal false. Unknown fields and modes are rejected. Loading configuration does
not load a fixture, access PG, or create a provider. The existing private reader
enforces no-follow, ownership, 0600 and the original 32768-byte bound.

No file means no inquiry router and no supported inquiry workflow in the Worker.
Explicit configuration requires the original Web session configuration. The API
installs the reviewed router, exposes its separate OpenAPI at
`app.state.inquiry_openapi`, and preserves the existing public OpenAPI exactly.
Only the three explicitly declared inquiry paths are removed from the legacy
export; unknown legacy paths still fail the original export gate. Session,
Origin, CSRF and permission failures at the shared boundary use the inquiry's
strict error DTO for this namespace. Existing routes retain their original DTOs.

The composite runner adds the actual `ReadonlyInquiryRunner` to the existing
serial slot; it does not create another Worker, scheduler, or provider. Runtime
bootstrap grants only SELECT/INSERT and the six controlled UPDATE columns on the
inquiry table when that table exists, including when the role is first created
after migration. No DELETE/TRUNCATE or request-column UPDATE is granted.

Termination attention handling excludes only the exact inquiry workflow's
completed/failed tasks with a database-verified durable result. The query adds
this predicate only when the exact validation function exists, preserving older
migration paths. Corrupt or nonterminal results receive no new exemption.

Author checks: 78 targeted offline tests passed, including actual ASGI middleware
with an authentication double and an actual composite-slot concurrency test;
Ruff/format and strict mypy on eight files passed. This does not prove SQL grants,
real session authentication, job recovery, or an API/Worker process lifecycle.
The first probe had two failures (lazy router inspection and OpenAPI invalidation);
the revised probe then had one failure because a nonexistent DB was used for
authentication. The final boundary test explicitly injects an authentication
failure and checks the real middleware's typed 401/403 response, without PG.

The existing local inquiry SQL batch's 25 pass/11 fail result remains unresolved
by this wiring. A later exact SQL fix and new owned integrated validation are
required. No services, PG, models, Feishu messages, push, or Hosted CI were started
by these author checks. Knowledge/copy registration is a separate subsequent
integration after its strict response contract is frozen.
