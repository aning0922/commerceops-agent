"""Host bridge for fixed real app-role probes; no owner authority or fake HTTP results."""

import base64
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from tests.e2e.v4.owned_adapter import compose_environment
from tests.e2e.v4.owned_driver import private

from .http_recipes import Business, import_bytes
from .runner import persist
from .subjects import registry


def run_probes(business: Business) -> None:
    current = business.visitor.current
    if current is None or current["data"]["persona_id"] != "operator":
        raise ValueError("CURRENT_PROBE_IDENTITY_REQUIRED")
    page = business.call("products")["data"]
    product = page["items"][0]
    body = business.write(
        page["snapshot"]["data_revision"],
        expected_version=product["version"],
        tags=["QA rollback only"],
    )
    preview = business.write(
        page["snapshot"]["data_revision"],
        format="csv",
        filename="probe.csv",
        file_base64=base64.b64encode(
            import_bytes("csv", "QA-" + uuid4().hex[:12], business.shop["currency"])
        ).decode(),
        mapping={"sku": "sku", "title": "title", "price": "price", "currency": "currency"},
        mapping_version=1,
        parent_job_id=None,
    )
    scope = {
        n: current["context"][n]
        for n in ("tenant_id", "organization_id", "principal_id", "reset_epoch", "auth_generation")
    }
    scope["shop_id"] = business.shop["shop_id"]
    business.facts()  # Owner-only actual catalog binding; app never reads alembic_version.
    if business.last_owner_observation is None:
        raise ValueError("ACTUAL_OWNER_CATALOG_BINDING_REQUIRED")
    directory = Path(business.case.directory)
    path = directory / "api/v41-probe.private.json"
    token = business.visitor.client.cookies.get("commerceops_v4_demo")
    if token is None:
        raise ValueError("NEW_OWNED_PROBE_COOKIE_REQUIRED")
    private(
        path,
        json.dumps(
            {
                "schema": "v41-sql-probe-1",
                "owner_catalog": business.last_owner_observation,
                "source_sha": business.case.source_sha,
                "source_tree": business.case.source_tree,
                "scope": scope,
                "resource_id": product["product_id"],
                "body": body,
                "preview_body": preview,
                "bearer": token,
                "csrf": current["data"]["csrf_token"],
                "deadline": business.case.deadline,
            }
        ),
    )
    for operation, command in (("preview", preview), ("product_tags", body)):
        registry(
            directory,
            current["context"],
            business.shop["shop_id"],
            operation=operation,
            key=command["request_key"],
        )
    for action in ("binding-stop-attack", "forced-action-rollback"):
        output = directory / (action + ".stdout.private.log")
        error = directory / (action + ".stderr.private.log")
        record: dict[str, Any] = {
            "scope": "REAL_APP_SQL_PROBE",
            "action": action,
            "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "native_exit": None,
            "source_sha": business.case.source_sha,
            "source_tree": business.case.source_tree,
            "started_utc": datetime.now(UTC).isoformat(),
            "timed_out": False,
        }
        try:
            with output.open("xb") as out, error.open("xb") as err:
                output.chmod(0o600)
                error.chmod(0o600)
                result = subprocess.run(
                    [
                        *business.compose,
                        "exec",
                        "-T",
                        "v4-api",
                        "python",
                        "-m",
                        "tests.e2e.v41.sql_probes",
                        action,
                        "--root-opened-window",
                    ],
                    env=compose_environment(),
                    stdout=out,
                    stderr=err,
                    timeout=business.budget.timeout(30),
                    check=False,
                )
            record["native_exit"] = result.returncode
            if result.returncode:
                raise RuntimeError("SQL_PROBE_FAILED_OR_UNKNOWN_NO_RETRY")
            facts = json.loads(output.read_text())
            if facts["scope"] != scope or facts["before"] != facts["after"]:
                raise AssertionError("SQL_PROBE_SCOPE_OR_ROLLBACK_MISMATCH")
            if action == "binding-stop-attack":
                if facts["findings"] or facts["status"] != "FORGED_RESERVE_REJECTED":
                    raise AssertionError("SQL_ATTACK_ACCEPTED")
                operation, original_key = "preview", preview["request_key"]
            else:
                if not facts["rolled_back"] or facts["request_key"] != body["request_key"]:
                    raise AssertionError("SQL_FORCED_ROLLBACK_NOT_VERIFIED")
                operation, original_key = "product_tags", body["request_key"]
            lookup = business.call(
                "preview_lookup" if operation == "preview" else "receipt",
                ids={"request_key": original_key}
                if operation == "preview"
                else {"operation": operation, "request_key": original_key},
            )["data"]
            if (
                lookup["status"] != "UNKNOWN"
                or lookup["job" if operation == "preview" else "receipt"] is not None
            ):
                raise AssertionError("SQL_ROLLBACK_ORIGINAL_KEY_HTTP_NOT_UNKNOWN")
            registry(
                directory,
                current["context"],
                business.shop["shop_id"],
                operation=operation,
                key=original_key,
                state="SQL_ROLLBACK_VERIFIED",
            )
        except Exception as failure:
            record["failure"] = {
                "type": type(failure).__name__,
                "errno": getattr(failure, "errno", None),
            }
            record["timed_out"] = isinstance(failure, subprocess.TimeoutExpired)
            raise
        finally:
            record["finished_utc"] = datetime.now(UTC).isoformat()
            record["logs"] = [
                {"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                for p in (output, error)
                if p.is_file()
            ]
            persist(directory / (action + ".safe.json"), record)
