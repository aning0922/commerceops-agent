"""Actual host-side V4 adapter; PG is reachable only via named owned observers."""

import json
import subprocess
from dataclasses import fields
from pathlib import Path
from typing import Any
from uuid import uuid4

from .adapter import CapacityFacts, OperationFacts, Snapshot
from .strict_response import validate_response
from .supervisor import Budget, Role


class OwnedAdapter:
    def __init__(self, compose: tuple[str, ...], project: str, budget: Budget) -> None:
        self.compose, self.project, self.budget = compose, project, budget

    def validate_response(self, operation: str, status: int, payload: Any) -> None:
        validate_response(operation, status, payload, self.budget)

    def _facts(self, *args: str, final: bool = False) -> dict[str, Any]:
        # Name is registered before launch. The enclosing driver cleans only this
        # initially empty project, including timed-out one-off containers.
        name = f"{self.project}-facts-{uuid4().hex[:12]}"
        command = [
            *self.compose,
            "run",
            "--rm",
            "--no-deps",
            "--name",
            name,
            "pg-test",
            "python",
            "-m",
            "tests.e2e.v4.owned_pg_probe",
            *args,
            "--deadline",
            self.budget.deadline.isoformat(),
        ]
        if final:
            command.append("--final")
        process = subprocess.run(
            command,
            capture_output=True,
            env=compose_environment(),
            timeout=self.budget.timeout(12, cleanup=final),
            check=False,
        )
        if process.returncode:
            raise RuntimeError("owned PG observer failed; retain UNKNOWN")
        value = json.loads(process.stdout)
        if not isinstance(value, dict):
            raise ValueError("PG fact object required")
        return value

    def snapshot(self, tenant_id: str, *, final_collection: bool = False) -> Snapshot:
        return Snapshot(**self._facts("snapshot", "--tenant", tenant_id, final=final_collection))

    def capacity_facts(self) -> CapacityFacts:
        return CapacityFacts(**self._facts("capacity"))

    def operation_facts(self, operation: str, key: str) -> OperationFacts:
        row = self._facts("operation", "--operation", operation, "--key", key)
        if set(row) != {f.name for f in fields(OperationFacts)}:
            raise ValueError("operation fact fields mismatch")
        kinds = row["event_kinds"]
        if not isinstance(kinds, list) or any(type(kind) is not str for kind in kinds):
            raise ValueError("complete event array required")
        row["event_kinds"] = tuple(kinds)
        return OperationFacts(**row)

    def persona_ids(self) -> tuple[str, str]:
        return "approver", "restricted_admin"

    def tenant_ids(self, *, final: bool = False) -> list[str]:
        from uuid import UUID

        row = self._facts("tenants", final=final)
        if set(row) != {"tenants"} or not isinstance(row["tenants"], list):
            raise ValueError("tenant inventory required")
        for tenant in row["tenants"]:
            UUID(tenant)
        return list(row["tenants"])

    def bootstrap_facts(self, key: str) -> dict[str, Any]:
        return self._facts("bootstrap", "--key", key)

    def revoke_credential(self, tenant: str, principal: str) -> None:
        if self._facts("credential-revoke", "--tenant", tenant, "--principal", principal) != {
            "revoked": 1
        }:
            raise AssertionError("owned credential fixture revoke failed")

    def revoke_grant(self, tenant: str, principal: str, shop: str) -> None:
        if self._facts(
            "grant-revoke", "--tenant", tenant, "--principal", principal, "--shop", shop
        ) != {"revoked": 1, "remaining": 1}:
            raise AssertionError("owned shop grant fixture revoke failed")

    def launch_spec(self, role: Role) -> tuple[tuple[str, ...], dict[str, str]]:
        if role != "api":
            raise ValueError("host WEB/probe launch is explicitly bound by the owned driver")
        return (
            *self.compose,
            "up",
            "--no-build",
            "--pull",
            "never",
            "v4-api",
        ), compose_environment()


def compose_environment() -> dict[str, str]:
    # Docker context/socket selection is an explicit local host prerequisite, not
    # inherited cloud/DB/provider config. No owner environment reaches the API.
    environment = {"PATH": "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"}
    environment["HOME"] = str(Path.home())
    return environment
