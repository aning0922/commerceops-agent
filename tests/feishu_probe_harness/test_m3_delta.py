import json
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest

from scripts.feishu_probe_harness import m3_delta as leaf

from .test_card_readback import fixture

pytestmark = pytest.mark.offline


def material() -> Any:
    body, plans, cards, receipts, keys = fixture()
    pid = UUID(plans["m3"].probe_id)
    before = json.loads(
        leaf.canonical(
            dict(
                cards=list(cards.values()),
                receipts=[r for rs in receipts.values() for r in rs],
                event_keys=[dict(receipt_id=k, keys=v) for k, v in keys.items()],
                snapshot_validation="VERIFIED_DIAGNOSTIC_NOT_GATE",
            )
        )
    )
    scoped = dict(
        identity=body["identity"],
        plan=body["plans"]["m3"],
        bot_open_id=body["bot_open_id"],
        before_sha256="0" * 64,
    )
    settings = SimpleNamespace(
        user="commerceops_app", host="postgres", name="commerceops", port=5432
    )
    return (scoped, settings, before, pid, cards, receipts, keys)


class Conn:
    def __init__(
        self: Any, pid: Any, cards: Any, receipts: Any, keys: Any, role: Any = "commerceops_app"
    ) -> None:
        self.pid, self.cards, self.receipts, self.keys, self.role = (
            pid,
            cards,
            receipts,
            keys,
            role,
        )
        self.queries: list[Any] = []

    def __enter__(self: Any) -> Any:
        return self

    def __exit__(self: Any, *args: Any) -> Any:
        return False

    def execute(self: Any, query: Any, params: Any = ()) -> Any:
        text = str(query)
        self.queries.append((text, params))
        if text.startswith("SET "):
            return SimpleNamespace()
        if text.startswith("SELECT current_user"):
            return SimpleNamespace(
                fetchone=lambda: dict(
                    role=self.role,
                    database="commerceops",
                    readonly="on",
                    isolation="repeatable read",
                )
            )
        assert "FOR UPDATE" not in text and "FOR SHARE" not in text
        assert "business." not in text and "base_operations" not in text
        if "FROM feishu_probe.cards" in text:
            assert params[0] == self.pid
            assert params[1:] == (
                self.cards[self.pid]["organization_id"],
                self.cards[self.pid]["shop_id"],
            )
            return SimpleNamespace(fetchall=lambda: [self.cards[self.pid]])
        if "FROM feishu_probe.receipts" in text:
            assert params[2] == self.pid and "LIMIT 65" in text
            return SimpleNamespace(fetchall=lambda: self.receipts[self.pid])
        assert "FROM feishu_probe.event_keys" in text and params[0] in {
            r["id"] for r in self.receipts[self.pid]
        }
        return SimpleNamespace(fetchall=lambda: self.keys[params[0]])


def test_one_M3_unchanged_full_snapshot_and_original_validator() -> Any:
    body, settings, before, pid, cards, receipts, keys = material()
    c = Conn(pid, cards, receipts, keys)
    written: Any = []
    result = leaf.inspect_m3(
        body,
        settings,
        before,
        connector=lambda _: c,
        archive_writer=lambda value: written.append(value) or "0" * 64,
    )
    assert result["receipt_count"] == result["event_key_count"] == 3
    assert result["full_prior_snapshot_unchanged"] is True
    assert result["full_card_binding_verified"] is True
    assert len(written) == 1 and len(written[0]["cards"]) == 1
    assert len(c.queries) == 10


@pytest.mark.parametrize(
    "change",
    [
        "decision",
        "missing_receipt",
        "event_key",
        "scope",
        "unverified_before",
        "wrong_role",
        "missing_card",
    ],
)
def test_changed_or_untrusted_snapshot_rejected_before_archive(change: Any) -> Any:
    body, settings, before, pid, cards, receipts, keys = material()
    old = next(c for c in before["cards"] if c["id"] == str(pid))
    role = "commerceops_app"
    if change == "decision":
        old["decision"] = "reject_assumptions"
    if change == "missing_receipt":
        before["receipts"] = [
            r for r in before["receipts"] if r["id"] != str(receipts[pid][0]["id"])
        ]
    if change == "event_key":
        before["event_keys"] = []
    if change == "scope":
        old["shop_id"] = str(UUID(int=1))
    if change == "unverified_before":
        before["snapshot_validation"] = "INCOMPLETE"
    if change == "wrong_role":
        role = "commerceops_owner"
    if change == "missing_card":
        before["cards"] = []
    c = Conn(pid, cards, receipts, keys, role)
    written: Any = []
    with pytest.raises(ValueError):
        leaf.inspect_m3(
            body,
            settings,
            before,
            connector=lambda _: c,
            archive_writer=lambda value: written.append(value),
        )
    assert written == []


def test_receipt_limit_fails_before_archive() -> Any:
    body, settings, before, pid, cards, receipts, keys = material()
    receipts[pid] = receipts[pid] * 22
    c = Conn(pid, cards, receipts, keys)
    with pytest.raises(ValueError):
        leaf.inspect_m3(
            body,
            settings,
            before,
            connector=lambda _: c,
            archive_writer=lambda _: pytest.fail("archive"),
        )


def test_owner_settings_fail_before_connection() -> Any:
    body, settings, before, pid, cards, receipts, keys = material()
    settings.user = "commerceops_owner"
    with pytest.raises(ValueError):
        leaf.inspect_m3(body, settings, before, connector=lambda _: pytest.fail("connection"))
