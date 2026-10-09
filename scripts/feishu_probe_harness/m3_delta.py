"""M3 DB故障后只读差异核心；公开适配版仅离线测试。"""

import hashlib
import json
import re
from datetime import datetime
from typing import Any
from uuid import UUID

from commerceops.adapters.feishu.contracts import ProbePlan
from commerceops.infrastructure.database import connect

from .card_readback import validate_rows


def write_archive(body: Any) -> Any:
    raise ValueError("explicit archive writer required")


def plan_from(body: Any) -> Any:
    plan = dict(body)
    plan["expires_at"] = datetime.fromisoformat(plan["expires_at"])
    plan["required_assumption_keys"] = tuple(plan["required_assumption_keys"])
    return ProbePlan(**plan)


def canonical(value: Any) -> Any:

    def scalar(item: Any) -> Any:
        if isinstance(item, (UUID, datetime)):
            return str(item)
        raise ValueError()

    return json.dumps(value, sort_keys=True, default=scalar).encode()


def inspect_m3(
    body: Any,
    settings: Any,
    before_raw: Any,
    connector: Any = connect,
    archive_writer: Any = write_archive,
) -> Any:
    if set(body) != {"identity", "plan", "bot_open_id", "before_sha256"}:
        raise ValueError()
    if (settings.user, settings.host, settings.name, settings.port) != (
        "commerceops_app",
        "postgres",
        "commerceops",
        5432,
    ):
        raise ValueError()
    digest = body["before_sha256"]
    if (
        not isinstance(digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        or not isinstance(before_raw, bytes)
        or len(before_raw) > 1048576
        or hashlib.sha256(before_raw).hexdigest() != digest
    ):
        raise ValueError()
    before = json.loads(before_raw)
    if (
        not isinstance(before, dict)
        or before.get("snapshot_validation") != "VERIFIED_DIAGNOSTIC_NOT_GATE"
    ):
        raise ValueError()
    plan = plan_from(body["plan"])
    org, shop = (body["identity"]["organization"], body["identity"]["shop"])
    old_cards = [c for c in before["cards"] if c["id"] == plan.probe_id]
    if len(old_cards) != 1:
        raise ValueError()
    old_card = old_cards[0]
    if old_card["organization_id"] != org["id"] or old_card["shop_id"] != shop["id"]:
        raise ValueError()
    old_receipts = [r for r in before["receipts"] if r["probe_id"] == plan.probe_id]
    old_ids = {r["id"] for r in old_receipts}
    old_keys = [k for k in before["event_keys"] if k["receipt_id"] in old_ids]
    expected = dict(cards=old_cards, receipts=old_receipts, event_keys=old_keys)
    with connector(settings) as c:
        c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        c.execute("SET LOCAL statement_timeout='1000ms'")
        c.execute("SET LOCAL lock_timeout='200ms'")
        c.execute("SET LOCAL transaction_timeout='10000ms'")
        mode = c.execute(
            "SELECT current_user AS role,current_database() AS database,"
            "current_setting('transaction_read_only') AS readonly,"
            "current_setting('transaction_isolation') AS isolation"
        ).fetchone()
        if mode != dict(
            role="commerceops_app",
            database="commerceops",
            readonly="on",
            isolation="repeatable read",
        ):
            raise ValueError()
        cards = c.execute(
            "SELECT * FROM feishu_probe.cards WHERE id=%s AND organization_id=%s AND shop_id=%s",
            (UUID(plan.probe_id), UUID(org["id"]), UUID(shop["id"])),
        ).fetchall()
        if len(cards) != 1:
            raise ValueError()
        card = cards[0]
        receipts = c.execute(
            "SELECT * FROM feishu_probe.receipts WHERE organization_id=%s AND shop_id=%s "
            "AND (probe_id=%s OR sanitized_payload->>'probe_id'=%s OR context_message_id=%s "
            "OR sanitized_payload->>'context_message_id'=%s) ORDER BY created_at,id LIMIT 65",
            (
                UUID(org["id"]),
                UUID(shop["id"]),
                UUID(plan.probe_id),
                plan.probe_id,
                card["message_id"],
                card["message_id"],
            ),
        ).fetchall()
        if len(receipts) > 64:
            raise ValueError()
        key_map, keys = ({}, [])
        for row in receipts:
            values = c.execute(
                "SELECT app_id,tenant_key,event_id,receipt_id "
                "FROM feishu_probe.event_keys WHERE receipt_id=%s",
                (row["id"],),
            ).fetchall()
            key_map[row["id"]] = values
            keys.append(dict(receipt_id=row["id"], keys=values))
        diagnostic = validate_rows(
            "m3", plan, card, receipts, key_map, body["identity"], body["bot_open_id"]
        )
        after = dict(cards=cards, receipts=receipts, event_keys=keys)
        if canonical(expected) != canonical(after):
            raise ValueError()
    digest = archive_writer(after)
    return dict(
        status="M3_DB_FAILURE_DELTA_READONLY_VERIFIED_NOT_GATE",
        readonly=True,
        repeatable_read=True,
        only_M3_three_probe_tables=True,
        full_prior_snapshot_unchanged=True,
        receipt_count=diagnostic["receipt_count"],
        event_key_count=diagnostic["event_key_count"],
        full_card_binding_verified=diagnostic["full_card_binding_verified"],
        private_archive_sha256=digest,
        no_SQL_write_locking_select_SDK_API_WS_card=True,
        G3="INCOMPLETE",
    )
