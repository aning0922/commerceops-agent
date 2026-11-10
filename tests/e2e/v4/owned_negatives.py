"""Additional real V4 HTTP/owned-fixture negatives. Never executed on import."""

from uuid import uuid4

from .http_probe import FIXTURE, PREFIX, Visitor, capacity_rejection, snapshot_cookies
from .owned_adapter import OwnedAdapter
from .supervisor import Budget


def uncommitted_bootstrap(reply: dict[str, object], key: str) -> None:
    if reply["data"] != {
        "operation": "session_create",
        "request_key": key,
        "status": "UNKNOWN",
        "recovery": "WAIT_READ_ONLY",
    }:
        raise AssertionError("uncommitted original key must retain minimal UNKNOWN readback")


def run_owned_negative(
    name: str, api: str, origin: str, budget: Budget, adapter: OwnedAdapter
) -> None:
    if name not in {"bootstrap_restart", "identity_scopes", "credential_revoke", "grant_revoke"}:
        raise ValueError("explicit owned negative required")
    visitors = [
        Visitor(api, origin, budget, adapter)
        for _ in range(4 if name == "bootstrap_restart" else 1)
    ]
    try:
        if name == "bootstrap_restart":
            for visitor in visitors[:3]:
                visitor.create()
            visitor = visitors[3]
            csrf = visitor.bootstrap()
            old_cookie = snapshot_cookies(visitor.client.cookies)
            first_key = str(uuid4())

            def denied(key: str, supplied: str) -> None:
                response = visitor.client.post(
                    PREFIX + "/sessions",
                    json={"request_key": key, "fixture_version": FIXTURE},
                    headers={"Origin": origin, "X-CSRF-Token": supplied},
                    timeout=budget.timeout(10),
                )
                reply = visitor.check("createDemoSession", response, (429,))
                capacity_rejection(reply, response.headers.get("retry-after"))
                if reply["status"] != "REJECTED":
                    raise AssertionError("deterministic REJECTED required before explicit restart")

            denied(first_key, csrf)
            before = adapter.bootstrap_facts(first_key)
            if before["key"] != first_key or before["consumed"]:
                raise AssertionError("original bound/unconsumed owner required")
            # Represents an explicit user re-entry, never an UNKNOWN retry policy.
            fresh_csrf = visitor.bootstrap()
            new_cookie = snapshot_cookies(visitor.client.cookies)
            if [(c.name, c.value) for c in old_cookie.jar] == [
                (c.name, c.value) for c in new_cookie.jar
            ]:
                raise AssertionError("bound bootstrap owner was incorrectly reused")
            next_key = str(uuid4())
            denied(next_key, fresh_csrf)
            if adapter.bootstrap_facts(first_key) != before:
                raise AssertionError("original bootstrap binding changed")
            if adapter.bootstrap_facts(next_key)["id"] == before["id"]:
                raise AssertionError("explicit re-entry did not get a new bootstrap owner")
            visitor.client.cookies = snapshot_cookies(old_cookie)
            response = visitor.client.get(
                f"{PREFIX}/operations/session_create/{first_key}",
                headers={"Origin": origin},
                timeout=budget.timeout(10),
            )
            unknown = visitor.check("readDemoControlReceipt", response, (200,))
            uncommitted_bootstrap(unknown, first_key)
            from .adapter import CapacityFacts

            if adapter.capacity_facts() != CapacityFacts(3, 3, 3):
                raise AssertionError("restart silently created an extra tenant")
            for active in visitors[:3]:
                active.read_current()
        else:
            visitor = visitors[0]
            current = visitor.create()
            if name == "grant_revoke":
                shop = current["data"]["shops"][0]["shop_id"]
                adapter.revoke_grant(
                    current["context"]["tenant_id"], current["context"]["principal_id"], shop
                )
                # Existing P3 grant-change triggers advance auth_version.
                # Both old bound-session reads must fail, despite one grant remaining.
                visitor.read_current(expected=(401,))
                visitor.current = current
                for old_shop in current["data"]["shops"]:
                    visitor.summary(old_shop["shop_id"], expected=(401,))
            elif name == "credential_revoke":
                adapter.revoke_credential(
                    current["context"]["tenant_id"], current["context"]["principal_id"]
                )
                visitor.read_current(expected=(401,))
                visitor.call(
                    "resetCurrentDemoTenant",
                    body={
                        "request_key": str(uuid4()),
                        "fixture_version": FIXTURE,
                        "expected_epoch": current["context"]["reset_epoch"],
                        "expected_generation": current["context"]["auth_generation"],
                    },
                    headers={"X-CSRF-Token": current["data"]["csrf_token"]},
                    expected=(401,),
                )
            else:
                original_shops = {s["shop_id"] for s in current["data"]["shops"]}
                visitor.control("switchDemoPersona", persona_id="approver")
                approver = visitor.read_current()
                allowed = {s["shop_id"] for s in approver["data"]["shops"]}
                if len(original_shops) != 2 or len(allowed) != 1 or not allowed < original_shops:
                    raise AssertionError("approver must have exactly one explicitly granted shop")
                for shop in allowed:
                    visitor.summary(shop)
                for shop in original_shops - allowed:
                    visitor.summary(shop, expected=(404,))
                visitor.control("switchDemoPersona", persona_id="restricted_admin")
                if visitor.read_current()["data"]["shops"]:
                    raise AssertionError("admin has implicit business grants")
                visitor.control("resetCurrentDemoTenant", fixture_version=FIXTURE)
                after = visitor.read_current()
                if after["data"]["persona_id"] != "restricted_admin" or after["data"]["shops"]:
                    raise AssertionError("reset restored implicit admin/operator permissions")
                for shop in original_shops:
                    visitor.summary(shop, expected=(404,))
    finally:
        for visitor in visitors:
            visitor.close()
