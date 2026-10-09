"""剩余卡片批次：原DAL单委托，C纯合同/资格与原拒绝同callback同事务证据。"""

from contextlib import contextmanager
from typing import Any
from uuid import UUID

from commerceops.adapters.feishu.contracts import (
    ContractCode,
    ProbeBinding,
    ProbeContractError,
    parse_card,
)
from commerceops.adapters.feishu.repository import ProbeRepository


class WitnessReceiver:
    def __init__(
        self: Any,
        connections: Any,
        scope: Any,
        policy: Any,
        trace: Any,
        members: Any,
        identity: Any,
        allowed_C_probe: Any,
        sink: Any,
    ) -> None:
        self.connections, self.scope, self.policy, self.trace = (connections, scope, policy, trace)
        self.members, self.identity, self.allowed_C_probe, self.sink = (
            members,
            identity,
            allowed_C_probe,
            sink,
        )
        self.normal = ProbeRepository(connections, scope, policy)

    def receive_message(self: Any, payload: Any) -> Any:
        return self.normal.receive_message(payload)

    def receive_card(self: Any, payload: Any) -> Any:
        try:
            is_C = payload.get("event", {}).get("operator", {}).get("open_id") == self.members["C"]
        except (AttributeError, TypeError):
            is_C = False
        if not is_C:
            return self.normal.receive_card(payload)
        current = getattr(self.trace.context, "record", None)
        evidence = dict(
            schema="C1_SAME_CALLBACK_WITNESS_V1",
            callback_seq=current.get("seq") if current else None,
            actor="C",
            same_original_DAL_connection=False,
            principal_identity_scope_locked=False,
            enabled_and_roles_empty=False,
            pure_full_binding_value_context_valid=False,
            original_DAL_identity_denied=False,
            original_exception_propagated=False,
            context_rolled_back_after_original_denial=False,
            qualified=False,
            wire_observed=False,
            human_Toast_observed=False,
        )
        observed_error = None

        @contextmanager
        def witnessed_connection() -> Any:
            try:
                with self.connections() as connection:
                    evidence["same_original_DAL_connection"] = True
                    connection.execute("SAVEPOINT c1_witness")
                    try:
                        self.validate_C(connection, payload, evidence)
                        connection.execute("RELEASE SAVEPOINT c1_witness")
                    except Exception:
                        connection.execute("ROLLBACK TO SAVEPOINT c1_witness")
                        connection.execute("RELEASE SAVEPOINT c1_witness")
                        evidence["pure_full_binding_value_context_valid"] = False
                    yield connection
            except ProbeContractError as error:
                if error.code == ContractCode.IDENTITY_DENIED:
                    evidence["context_rolled_back_after_original_denial"] = True
                raise

        original = ProbeRepository(witnessed_connection, self.scope, self.policy)
        try:
            return original.receive_card(payload)
        except BaseException as error:
            observed_error = error
            evidence["original_DAL_identity_denied"] = (
                isinstance(error, ProbeContractError) and error.code == ContractCode.IDENTITY_DENIED
            )
            evidence["original_exception_propagated"] = True
            raise
        finally:
            evidence["qualified"] = bool(
                evidence["callback_seq"] is not None
                and evidence["same_original_DAL_connection"]
                and evidence["principal_identity_scope_locked"]
                and evidence["enabled_and_roles_empty"]
                and evidence["pure_full_binding_value_context_valid"]
                and evidence["original_DAL_identity_denied"]
                and evidence["context_rolled_back_after_original_denial"]
                and (observed_error is not None)
            )
            try:
                self.sink(evidence)
            except Exception:
                evidence["qualified"] = False
                self.trace.incomplete = True

    def validate_C(self: Any, c: Any, payload: Any, e: Any) -> Any:
        member = next(m for m in self.identity["members"] if m["alias"] == "C")
        row = c.execute(
            """SELECT p.id,p.enabled,p.roles,p.auth_version,i.external_subject,
        i.app_id,i.tenant_key FROM business.principals p JOIN business.identities i
        ON i.organization_id=p.organization_id AND i.principal_id=p.id
        JOIN business.organizations o ON o.id=p.organization_id
        JOIN business.shops s ON s.organization_id=o.id
        WHERE o.id=%s AND s.id=%s AND i.provider='feishu' AND i.app_id=%s AND i.tenant_key=%s
        AND i.external_subject=%s AND p.id=%s AND o.feishu_app_id=i.app_id
        AND o.feishu_tenant_key=i.tenant_key FOR SHARE OF p,i,o,s""",
            (
                self.scope.organization_id,
                self.scope.shop_id,
                self.policy.app_id,
                self.policy.tenant_key,
                self.members["C"],
                UUID(member["principal_id"]),
            ),
        ).fetchone()
        if (
            row is None
            or row["id"] != UUID(member["principal_id"])
            or row["enabled"] is not True
            or (row["roles"] != [])
            or (row["auth_version"] != member["auth_version"])
            or (row["external_subject"] != self.members["C"])
            or (row["app_id"] != self.policy.app_id)
            or (row["tenant_key"] != self.policy.tenant_key)
        ):
            return
        e["principal_identity_scope_locked"] = True
        e["enabled_and_roles_empty"] = True
        pid = UUID(payload["event"]["action"]["value"]["probe_id"])
        if pid != self.allowed_C_probe:
            return
        card = c.execute(
            "SELECT * FROM feishu_probe.cards WHERE id=%s AND organization_id=%s "
            "AND shop_id=%s FOR SHARE",
            (pid, self.scope.organization_id, self.scope.shop_id),
        ).fetchone()
        if card is None or card["send_status"] != "sent":
            return
        expected = ProbeBinding(
            **{k: v for k, v in card["binding"].items() if k != "required_assumption_keys"},
            required_assumption_keys=tuple(card["binding"]["required_assumption_keys"]),
            nonce_sha256=card["nonce_sha256"],
            expires_at=card["expires_at"],
            chat_id=card["chat_id"],
            message_id=card["message_id"],
        )
        now = c.execute("SELECT clock_timestamp() AS checked_at").fetchone()["checked_at"]
        parsed = parse_card(payload, self.policy, expected, now)
        if parsed.identity.open_id != self.members["C"]:
            return
        e["pure_full_binding_value_context_valid"] = True


def expected_M3_candidate(records: Any) -> Any:
    actual = [
        (r["actor"], r["kind"], r["chat_kind"], r["result"], r["commit_return_observed"])
        for r in records
    ]
    return actual == [
        ("A", "card", "group", "probe_recorded:approve_with_assumptions", True),
        ("A", "card", "group", "duplicate_decision:approve_with_assumptions", True),
        ("B", "card", "group", "decision_conflict", True),
    ]


def hold_own_card_lock(
    connections: Any, scope: Any, probe_id: Any, stop: Any, ready: Any, seconds: Any = 60
) -> Any:
    if not 1 <= seconds <= 60:
        raise ValueError()
    with connections() as c:
        row = c.execute(
            "SELECT id FROM feishu_probe.cards WHERE id=%s AND organization_id=%s "
            "AND shop_id=%s FOR UPDATE",
            (probe_id, scope.organization_id, scope.shop_id),
        ).fetchone()
        if row is None:
            raise ValueError()
        ready.set()
        stop.wait(seconds)
    ready.clear()


def callback_mode_can_send(mode: Any) -> Any:
    return mode in ("m3", "c1")
