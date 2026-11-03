"""Real loopback HTTP/CookieJar probes. No mock transport, POST retries or CLI.

Call only inside a Root-approved owned window, with the exact reviewed adapter.
Transport failures remain UNKNOWN and escape; no subsequent mutation is attempted.
"""

import copy
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx

from .adapter import CapacityFacts, V4Adapter
from .supervisor import Budget

PREFIX = "/api/v4/demo"
FIXTURE = "v4-demo-seed-1"
PATHS = {
    "bootstrap": ("GET", "/bootstrap"),
    "createDemoSession": ("POST", "/sessions"),
    "readCurrentDemoSession": ("GET", "/session"),
    "switchDemoPersona": ("POST", "/persona"),
    "readDemoSeedSummary": ("GET", "/seed-summary"),
    "resetCurrentDemoTenant": ("POST", "/reset"),
    "logoutDemoSession": ("POST", "/logout"),
}


def receipt_binding(reply: dict[str, Any], operation: str, key: str) -> dict[str, Any]:
    data = reply["data"]
    receipt = data.get("receipt", data)
    if receipt.get("operation") != operation or receipt.get("request_key") != key:
        raise AssertionError("receipt operation/key mismatch")
    if "receipt" not in data and operation != "session_create":
        raise AssertionError("bootstrap recovery is session_create only")
    return dict(receipt)


def capacity_rejection(reply: dict[str, Any], retry_after: str | None) -> None:
    if (
        reply["error"]["code"] != "CAPACITY_LIMIT"
        or retry_after is None
        or not retry_after.isascii()
        or not retry_after.isdigit()
        or int(retry_after) <= 0
    ):
        raise AssertionError("capacity requires CAPACITY_LIMIT and positive Retry-After seconds")


def concurrent_reset_result(outcomes: list[tuple[int, dict[str, Any]]], key: str) -> dict[str, Any]:
    committed: list[dict[str, Any]] = []
    for status, reply in outcomes:
        if status == 200:
            receipt = receipt_binding(reply, "reset", key)
            if receipt["status"] != "COMMITTED":
                raise AssertionError("reset receipt not committed")
            committed.append(receipt)
        elif status != 403 or reply["error"]["code"] != "CSRF_INVALID":
            raise AssertionError("unexpected concurrent reset denial")
    if len(outcomes) != 2 or not committed:
        raise AssertionError("no successful reset HTTP observation; retain UNKNOWN")
    if any(receipt != committed[0] for receipt in committed):
        raise AssertionError("same key returned different receipt")
    return committed[0]


def loopback_origin(value: str) -> str:
    url = urlsplit(value)
    if (
        url.scheme != "http"
        or url.hostname != "127.0.0.1"
        or url.port is None
        or not 1024 <= url.port <= 65535
        or url.path not in {"", "/"}
        or url.query
        or url.fragment
        or url.username
        or url.password
    ):
        raise ValueError("explicit owned loopback HTTP origin required")
    return f"http://127.0.0.1:{url.port}"


class Visitor:
    def __init__(self, api: str, origin: str, budget: Budget, adapter: V4Adapter) -> None:
        self.api, self.origin = loopback_origin(api), loopback_origin(origin)
        self.budget, self.adapter = budget, adapter
        # Each visitor gets a real, independent CookieJar; redirects and proxies disabled.
        self.client = httpx.Client(
            base_url=self.api,
            trust_env=False,
            follow_redirects=False,
            transport=httpx.HTTPTransport(retries=0),
        )
        self.current: dict[str, Any] | None = None
        self.pending: tuple[str, str] | None = None

    def close(self) -> None:
        self.client.close()

    def call(
        self,
        operation: str,
        *,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        query: dict[str, str] | None = None,
        expected: tuple[int, ...] = (200,),
    ) -> dict[str, Any]:
        method, path = PATHS[operation]
        response = self.client.request(
            method,
            PREFIX + path,
            json=body,
            params=query,
            headers={"Origin": self.origin, **(headers or {})},
            timeout=self.budget.timeout(10),
        )
        return self.check(operation, response, expected)

    def check(
        self, operation: str, response: httpx.Response, expected: tuple[int, ...]
    ) -> dict[str, Any]:
        if response.status_code not in expected:
            raise AssertionError(f"{operation}: unexpected HTTP {response.status_code}")
        if "no-store" not in response.headers.get("cache-control", "").lower():
            raise AssertionError("sensitive response must be no-store")
        vary = {v.strip().lower() for v in response.headers.get("vary", "").split(",")}
        if not {"cookie", "origin"}.issubset(vary):
            raise AssertionError("Vary Cookie, Origin required")
        payload = response.json()
        self.adapter.validate_response(operation, response.status_code, payload)
        if not isinstance(payload, dict):
            raise AssertionError("strict object response required")
        return payload

    def bootstrap(self) -> str:
        return str(self.call("bootstrap")["data"]["csrf_token"])

    def create(self) -> dict[str, Any]:
        csrf, key = self.bootstrap(), str(uuid4())
        self.pending = ("session_create", key)
        reply = self.call(
            "createDemoSession",
            body={"request_key": key, "fixture_version": FIXTURE},
            headers={"X-CSRF-Token": csrf},
            expected=(200, 201),
        )
        if reply["data"]["receipt"]["request_key"] != key:
            raise AssertionError("creation receipt key mismatch")
        result = self.read_current()
        if result["data"]["creation_request_key"] != key:
            raise AssertionError("current creation key mismatch")
        self.check_cookie()
        self.pending = None
        return result

    def check_cookie(self) -> None:
        cookies = [c for c in self.client.cookies.jar if c.name == "commerceops_v4_demo"]
        if len(cookies) != 1:
            raise AssertionError("one V4-only cookie required")
        cookie = cookies[0]
        if cookie.path != "/api/v4" or not cookie.has_nonstandard_attr("HttpOnly"):
            raise AssertionError("V4 cookie Path/HttpOnly boundary missing")
        if cookie.get_nonstandard_attr("SameSite", "").lower() != "lax":
            raise AssertionError("SameSite=Lax required")
        # All supported origins here are explicit new-owned loopback HTTP.
        # This check does not claim TLS/Secure browser acceptance.

    def read_current(self, *, expected: tuple[int, ...] = (200,)) -> dict[str, Any]:
        self.current = None
        reply = self.call("readCurrentDemoSession", expected=expected)
        if "context" in reply:
            self.current = reply
        return reply

    def summary(self, shop_id: str, *, expected: tuple[int, ...] = (200,)) -> dict[str, Any]:
        if self.current is None:
            raise ValueError("verified current session required")
        context = self.current["context"]
        reply = self.call(
            "readDemoSeedSummary",
            query={"shop_id": shop_id},
            expected=expected,
            headers={
                "X-Demo-Epoch": str(context["reset_epoch"]),
                "X-Demo-Generation": str(context["auth_generation"]),
            },
        )
        if "context" in reply:
            observed = reply["context"]
            for name in (
                "tenant_id",
                "organization_id",
                "principal_id",
                "reset_epoch",
                "auth_generation",
            ):
                if observed[name] != context[name]:
                    raise AssertionError("stale/cross-owner context")
            if observed["shop_id"] != shop_id:
                raise AssertionError("shop context mismatch")
        return reply

    def control(self, operation: str, **payload: Any) -> dict[str, Any]:
        if operation not in {"switchDemoPersona", "resetCurrentDemoTenant", "logoutDemoSession"}:
            raise ValueError("V4 control operation required")
        if self.current is None:
            raise ValueError("verified current session required")
        current, self.current = self.current, None  # Clear before sending.
        key = str(uuid4())
        operation_name = {
            "switchDemoPersona": "persona",
            "resetCurrentDemoTenant": "reset",
            "logoutDemoSession": "logout",
        }[operation]
        self.pending = (operation_name, key)
        reply = self.call(
            operation,
            body={
                **payload,
                "request_key": key,
                "expected_epoch": current["context"]["reset_epoch"],
                "expected_generation": current["context"]["auth_generation"],
            },
            headers={"X-CSRF-Token": current["data"]["csrf_token"]},
        )
        receipt = reply["data"]["receipt"]
        if receipt["request_key"] != key or receipt["operation"] != operation_name:
            raise AssertionError("control receipt mismatch")
        self.pending = None
        return reply

    def receipt(self, operation: str, key: str) -> dict[str, Any]:
        if operation not in {"session_create", "persona", "reset", "logout"}:
            raise ValueError("control receipt only")
        # UUID validation prevents path injection; no arbitrary URL/operation adapter.
        UUID(key)
        response = self.client.get(
            f"{PREFIX}/operations/{operation}/{key}",
            headers={"Origin": self.origin},
            timeout=self.budget.timeout(10),
        )
        reply = self.check("readDemoControlReceipt", response, (200,))
        receipt_binding(reply, operation, key)
        return reply

    def create_ack_loss(self, loss: Literal["body", "headers_and_body"]) -> dict[str, Any]:
        if loss not in {"body", "headers_and_body"}:
            raise ValueError("explicit ACK-loss branch required")
        csrf, key = self.bootstrap(), str(uuid4())
        bootstrap_cookies = copy.deepcopy(self.client.cookies.jar)
        self.pending = ("session_create", key)
        # Real POST reaches PG; discard the actual response, never fabricate one.
        response = self.client.post(
            PREFIX + "/sessions",
            json={"request_key": key, "fixture_version": FIXTURE},
            headers={"Origin": self.origin, "X-CSRF-Token": csrf},
            timeout=self.budget.timeout(10),
        )
        response.close()
        if loss == "headers_and_body":
            self.client.cookies = httpx.Cookies(bootstrap_cookies)
        else:
            current = self.read_current()
            if current["data"]["creation_request_key"] != key:
                raise AssertionError("ACK recovery owner mismatch")
        receipt = self.receipt("session_create", key)
        observed = receipt_binding(receipt, "session_create", key)
        if observed["status"] != "COMMITTED":
            raise AssertionError("creation commit unverified; retain UNKNOWN")
        facts = self.adapter.operation_facts("session_create", key)
        # A creation receipt has one session_created and one seed_materialized event.
        if facts.receipts != 1 or facts.events != 2 or facts.tenant_id is None:
            raise AssertionError("creation not independently committed in PG")
        if loss == "body" and (
            facts.tenant_id != current["context"]["tenant_id"]
            or facts.receipt_id != observed["receipt_id"]
        ):
            raise AssertionError("ACK recovery does not match original PG commit")
        if loss == "headers_and_body":
            data = receipt["data"]
            if data != {
                "operation": "session_create",
                "request_key": key,
                "status": "COMMITTED",
                "recovery": "OWNER_RECOVERY_REQUIRED",
            }:
                raise AssertionError("unsafe bootstrap recovery or creation not observed")
            self.read_current(expected=(401,))
        return receipt


def lifecycle(a: Visitor, b: Visitor) -> None:
    """Two visitors, two stores, current identity, reset isolation and logout."""
    first, second = a.create(), b.create()
    tenant_a, tenant_b = first["context"]["tenant_id"], second["context"]["tenant_id"]
    if tenant_a == tenant_b:
        raise AssertionError("visitor tenant collision")
    for visitor, current in ((a, first), (b, second)):
        shops = current["data"]["shops"]
        if len(shops) != 2 or len({s["shop_id"] for s in shops}) != 2:
            raise AssertionError("default operator must have two explicitly granted shops")
        for shop in shops:
            visitor.summary(shop["shop_id"])
    a.summary(second["data"]["shops"][0]["shop_id"], expected=(404,))
    b.summary(first["data"]["shops"][0]["shop_id"], expected=(404,))
    before_b = b.adapter.snapshot(tenant_b)
    old_epoch = first["context"]["reset_epoch"]
    a.control("resetCurrentDemoTenant", fixture_version=FIXTURE)
    after = a.read_current()
    if after["context"]["reset_epoch"] != old_epoch + 1:
        raise AssertionError("reset must advance epoch exactly once")
    after_b = b.adapter.snapshot(tenant_b)
    if (
        after_b.digest,
        after_b.epoch,
        after_b.generation,
        after_b.receipts,
        after_b.tombstones,
    ) != (
        before_b.digest,
        before_b.epoch,
        before_b.generation,
        before_b.receipts,
        before_b.tombstones,
    ):
        raise AssertionError("A reset changed B")
    persona, _ = a.adapter.persona_ids()
    a.control("switchDemoPersona", persona_id=persona)
    if a.read_current()["data"]["persona_id"] != persona:
        raise AssertionError("server persona mismatch")
    a.control("logoutDemoSession")
    a.read_current(expected=(401,))


def capacity(visitors: list[Visitor]) -> None:
    """Run in an initially empty owned DB, separately from lifecycle/ACK cases."""
    if len(visitors) != 5 or len({id(v.client.cookies.jar) for v in visitors}) != 5:
        raise ValueError("five independent visitors required")
    adapter = visitors[0].adapter
    if adapter.capacity_facts() != CapacityFacts(0, 0, 0):
        raise AssertionError("capacity scenario requires empty owned DB")
    originals: list[tuple[str, str]] = []
    for visitor in visitors[:3]:
        current = visitor.create()
        originals.append((current["context"]["tenant_id"], current["data"]["creation_request_key"]))
    if len({tenant for tenant, _ in originals}) != 3:
        raise AssertionError("three distinct committed tenants required")
    if adapter.capacity_facts() != CapacityFacts(3, 3, 3):
        raise AssertionError("PG must observe three active tenants/sessions/creation receipts")
    for tenant, key in originals:
        facts = adapter.operation_facts("session_create", key)
        if facts.receipts != 1 or facts.events != 2 or facts.tenant_id != tenant:
            raise AssertionError("original capacity cohort creation not proven in PG")
    for visitor in visitors[3:]:
        csrf, key = visitor.bootstrap(), str(uuid4())
        response = visitor.client.post(
            PREFIX + "/sessions",
            json={"request_key": key, "fixture_version": FIXTURE},
            headers={"Origin": visitor.origin, "X-CSRF-Token": csrf},
            timeout=visitor.budget.timeout(10),
        )
        reply = visitor.check("createDemoSession", response, (429,))
        capacity_rejection(reply, response.headers.get("retry-after"))
        if adapter.operation_facts("session_create", key).receipts != 0:
            raise AssertionError("capacity-denied request committed a receipt")
    for visitor, original in zip(visitors[:3], originals, strict=True):
        current = visitor.read_current()
        if (current["context"]["tenant_id"], current["data"]["creation_request_key"]) != original:
            raise AssertionError("capacity denial displaced an original session")
    if adapter.capacity_facts() != CapacityFacts(3, 3, 3):
        raise AssertionError("capacity denial changed original active cohort")


def security_negatives(visitor: Visitor) -> None:
    """Real Origin/CSRF/strict payload boundary against an active owned visitor."""
    current = visitor.read_current()
    context = current["context"]
    body = {
        "request_key": str(uuid4()),
        "fixture_version": FIXTURE,
        "expected_epoch": context["reset_epoch"],
        "expected_generation": context["auth_generation"],
    }
    correct = {"Origin": visitor.origin, "X-CSRF-Token": current["data"]["csrf_token"]}
    for headers in (
        {"X-CSRF-Token": correct["X-CSRF-Token"]},
        {**correct, "Origin": "https://untrusted.invalid"},
        {**correct, "X-CSRF-Token": "deliberately-wrong-new-test-nonce"},
    ):
        response = visitor.client.post(
            PREFIX + "/reset",
            json={**body, "request_key": str(uuid4())},
            headers=headers,
            timeout=visitor.budget.timeout(10),
        )
        reply = visitor.check("resetCurrentDemoTenant", response, (403,))
        if reply["error"]["code"] not in {"ORIGIN_DENIED", "CSRF_INVALID"}:
            raise AssertionError("wrong rejection reason")
    visitor.call(
        "resetCurrentDemoTenant", body={**body, "role": "admin"}, headers=correct, expected=(422,)
    )
    after = visitor.read_current()
    if after["context"] != context:
        # authorized_at is freshly generated DB time, all identity fields must match.
        for name in context.keys() - {"authorized_at"}:
            if after["context"][name] != context[name]:
                raise AssertionError("rejected operation changed identity")
    cookie = visitor.client.cookies.get("commerceops_v4_demo")
    if not cookie:
        raise AssertionError("V4 bearer missing")
    with httpx.Client(
        base_url=visitor.api,
        trust_env=False,
        follow_redirects=False,
        transport=httpx.HTTPTransport(retries=0),
    ) as legacy:
        legacy.cookies.set("commerceops_session", cookie, domain="127.0.0.1", path="/api/v1")
        response = legacy.get(
            f"/api/v1/tasks/{uuid4()}",
            headers={"Origin": visitor.origin},
            timeout=visitor.budget.timeout(10),
        )
        if response.status_code != 401:
            raise AssertionError("renamed V4 bearer must fail legacy API authentication")


def same_key_reset(visitor: Visitor) -> None:
    """Adversarial duplicate/concurrent requests, not a browser retry policy."""
    current = visitor.read_current()
    key = str(uuid4())
    context = current["context"]
    body = {
        "request_key": key,
        "fixture_version": FIXTURE,
        "expected_epoch": context["reset_epoch"],
        "expected_generation": context["auth_generation"],
    }
    headers = {"X-CSRF-Token": current["data"]["csrf_token"]}
    visitor.current = None
    visitor.pending = ("reset", key)

    if visitor.adapter.operation_facts("reset", key).receipts != 0:
        raise AssertionError("new reset key already exists")

    def post() -> tuple[int, dict[str, Any]]:
        response = visitor.client.post(
            PREFIX + "/reset",
            json=body,
            headers={"Origin": visitor.origin, **headers},
            timeout=visitor.budget.timeout(10),
        )
        return response.status_code, visitor.check("resetCurrentDemoTenant", response, (200, 403))

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(post), pool.submit(post)]
        replies = [future.result(timeout=visitor.budget.timeout(12)) for future in futures]
    original_receipt = concurrent_reset_result(replies, key)
    updated = visitor.read_current()
    if updated["context"]["reset_epoch"] != context["reset_epoch"] + 1:
        raise AssertionError("duplicate reset had more than one effect")
    if receipt_binding(visitor.receipt("reset", key), "reset", key) != original_receipt:
        raise AssertionError("GET original receipt mismatch")
    new_headers = {"X-CSRF-Token": updated["data"]["csrf_token"]}
    # Explicit adversarial replay with current CSRF, never automatic browser retry.
    replay = visitor.call("resetCurrentDemoTenant", body=body, headers=new_headers)
    if receipt_binding(replay, "reset", key) != original_receipt:
        raise AssertionError("current-CSRF same-body replay changed receipt")
    conflict = visitor.call(
        "resetCurrentDemoTenant",
        body={**body, "expected_epoch": body["expected_epoch"] + 1},
        headers={"X-CSRF-Token": updated["data"]["csrf_token"]},
        expected=(409,),
    )
    if conflict["error"]["code"] != "IDEMPOTENCY_CONFLICT":
        raise AssertionError("same key/different digest must be an idempotency conflict")
    facts = visitor.adapter.operation_facts("reset", key)
    if (
        facts.receipts != 1
        or facts.events != 1
        or facts.receipt_id != original_receipt["receipt_id"]
        or facts.tenant_id != context["tenant_id"]
        or facts.epoch != context["reset_epoch"] + 1
    ):
        raise AssertionError("PG must prove original key one receipt/event and epoch +1")
    if visitor.read_current()["context"]["reset_epoch"] != facts.epoch:
        raise AssertionError("replay advanced epoch again")
    visitor.pending = None


def persona_stale_request(visitor: Visitor) -> None:
    current = visitor.read_current()
    old = current["context"]
    persona, _ = visitor.adapter.persona_ids()
    visitor.control("switchDemoPersona", persona_id=persona)
    new = visitor.read_current()
    if new["context"]["auth_generation"] <= old["auth_generation"]:
        raise AssertionError("persona must advance auth generation")
    body = {
        "request_key": str(uuid4()),
        "fixture_version": FIXTURE,
        "expected_epoch": old["reset_epoch"],
        "expected_generation": old["auth_generation"],
    }
    rejected = visitor.call(
        "resetCurrentDemoTenant",
        body=body,
        headers={"X-CSRF-Token": current["data"]["csrf_token"]},
        expected=(403,),
    )
    if rejected["error"]["code"] != "CSRF_INVALID":
        raise AssertionError("old persona CSRF must be invalidated")
    visitor.call(
        "resetCurrentDemoTenant",
        body={**body, "request_key": str(uuid4())},
        headers={"X-CSRF-Token": new["data"]["csrf_token"]},
        expected=(409,),
    )


def run_scenario(scenario: str, api: str, origin: str, budget: Budget, adapter: V4Adapter) -> None:
    """Probe-child entry: parent Supervisor must own/kill its whole process group.

    Each scenario requires its own initially empty owned database. Caller supplies
    the exact reviewed adapter; there is intentionally no implicit adapter import,
    DSN discovery, credentials, fallback or automatic scenario retry.
    """
    if scenario not in {
        "lifecycle",
        "capacity",
        "ack_body",
        "ack_headers",
        "security",
        "same_key_reset",
        "persona_stale",
    }:
        raise ValueError("explicit V4 scenario required")
    budget.timeout(1)
    visitors = [
        Visitor(api, origin, budget, adapter)
        for _ in range(5 if scenario == "capacity" else 2 if scenario == "lifecycle" else 1)
    ]
    try:
        if scenario == "capacity":
            capacity(visitors)
        elif scenario == "lifecycle":
            lifecycle(visitors[0], visitors[1])
        elif scenario in {"ack_body", "ack_headers"}:
            visitors[0].create_ack_loss("body" if scenario == "ack_body" else "headers_and_body")
        else:
            visitor = visitors[0]
            visitor.create()
            if scenario == "security":
                security_negatives(visitor)
            elif scenario == "same_key_reset":
                same_key_reset(visitor)
            else:
                persona_stale_request(visitor)
    finally:
        for visitor in visitors:
            visitor.close()
