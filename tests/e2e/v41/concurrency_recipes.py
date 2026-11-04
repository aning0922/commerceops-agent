"""Fixed real HTTP catalog races; never mocked transport or write retry."""

import copy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from typing import Any

from tests.e2e.v4.http_probe import Visitor, snapshot_cookies

from .http_recipes import Business
from .runner import persist


def receipts(outcomes: list[dict[str, Any]], *, same_key: bool) -> dict[str, Any]:
    if len(outcomes) != 2:
        raise AssertionError("V41_TWO_RACE_OBSERVATIONS_REQUIRED")
    committed = [r["data"]["receipt"] for r in outcomes if r["status"] == "COMMITTED"]
    rejected = [r for r in outcomes if r["status"] == "REJECTED"]
    if same_key:
        if len(committed) != 2 or committed[0] != committed[1]:
            raise AssertionError("V41_SAME_KEY_RACE_RECEIPT_DIVERGED")
    else:
        if len(committed) != 1 or len(rejected) != 1:
            raise AssertionError("V41_DISTINCT_KEY_RACE_NOT_SINGLE_WINNER")
        if rejected[0]["error"]["code"] not in {"VERSION_CONFLICT", "SNAPSHOT_CHANGED"}:
            raise AssertionError("V41_RACE_WRONG_CONFLICT")
    if any(r.get("operation") != "product_tags" for r in committed):
        raise AssertionError("V41_RACE_WRONG_OPERATION")
    return dict(committed[0])


def pair(
    business: Business, product_id: str, payloads: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    # Two independent real CookieJars bound to the same current session. No create,
    # switch or reset races occur implicitly; no requests are retried after failure.
    visitors = []
    for _ in range(2):
        visitor = Visitor(
            business.case.api, business.case.web, business.budget, business.visitor.adapter
        )
        visitor.current = copy.deepcopy(business.visitor.current)
        visitor.client.cookies = snapshot_cookies(business.visitor.client.cookies)
        visitors.append(visitor)
    barrier = Barrier(2)

    def request(index: int) -> dict[str, Any]:
        actor = Business(visitors[index], business.case, business.compose, business.budget)
        barrier.wait(timeout=business.budget.timeout(2))
        return actor.call(
            "tags", ids={"product_id": product_id}, payload=payloads[index], expected=(200, 409)
        )

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(request, i) for i in range(2)]
            return [future.result(timeout=business.budget.timeout(20)) for future in futures]
    finally:
        for visitor in visitors:
            visitor.close()


def catalog_concurrency(business: Business) -> None:
    results = []
    product_id = business.call("products")["data"]["items"][0]["product_id"]
    for same_key in (True, False):
        page = business.call("products")["data"]
        product = business.call("product", ids={"product_id": product_id})["data"]["product"]
        if product["version"] < 1:
            raise AssertionError("V41_CATALOG_TAG_ROW_SETUP_REQUIRED")
        before = business.facts()
        first = business.write(
            page["snapshot"]["data_revision"],
            expected_version=product["version"],
            tags=["QA concurrent same" if same_key else "QA contender A"],
        )
        second = (
            copy.deepcopy(first)
            if same_key
            else business.write(
                page["snapshot"]["data_revision"],
                expected_version=product["version"],
                tags=["QA contender B"],
            )
        )
        outcomes = pair(business, product["product_id"], [first, second])
        receipt = receipts(outcomes, same_key=same_key)
        if (
            receipt["request_key"] not in {first["request_key"], second["request_key"]}
            or receipt["resource_id"] != product["product_id"]
            or receipt["resource_version"] != product["version"] + 1
        ):
            raise AssertionError("V41_RACE_RECEIPT_IDENTITY_VERSION_MISMATCH")
        # Read both original keys, including the losing key. UNKNOWN never causes a POST.
        for body in (first, second):
            found = business.call(
                "receipt",
                ids={"operation": "product_tags", "request_key": body["request_key"]},
            )["data"]
            if body["request_key"] == receipt["request_key"]:
                if found["status"] != "COMMITTED" or found["receipt"] != receipt:
                    raise AssertionError("V41_RACE_WINNER_READBACK_MISMATCH")
            elif found["status"] != "UNKNOWN" or found["receipt"] is not None:
                raise AssertionError("V41_RACE_LOSER_HAS_EFFECT")
        final = business.call("product", ids={"product_id": product["product_id"]})["data"][
            "product"
        ]
        winner = first if receipt["request_key"] == first["request_key"] else second
        if final["version"] != product["version"] + 1 or final["tags"] != winner["tags"]:
            raise AssertionError("V41_RACE_EFFECT_VERSION_MISMATCH")
        for field in set(product) - {"version", "tags"}:
            if final[field] != product[field]:
                raise AssertionError("V41_RACE_CHANGED_PRICE_STOCK_OR_SOURCE")
        after = business.facts()
        for table in before:
            # The existing tag row is updated; receipts/events are each inserted once.
            increment = 1 if table in {"v41_action_receipts", "v41_action_events"} else 0
            if after[table] != before[table] + increment:
                raise AssertionError("V41_RACE_SCOPE_EFFECT_NOT_ONCE")
        results.append({"same_key": same_key, "receipt": receipt, "before": before, "after": after})
    persist(Path(business.case.directory) / "catalog-races.private.json", {"results": results})
