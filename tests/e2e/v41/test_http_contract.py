"""Actual Ajv against accepted schema + synthetic public files, no HTTP or PG."""

import copy
import csv
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from uuid import uuid4

import pytest
from defusedxml import ElementTree  # type: ignore[import-untyped]

from .http_recipes import import_bytes
from .process import ROOT

pytestmark = pytest.mark.offline
SCHEMA_SOURCE = "b72331fa572d9d67ad176902283da721aeda4cf1"


@pytest.mark.parametrize("kind", ["csv", "xlsx"])
def test_small_synthetic_import_retains_exact_sku_amount_and_currency(kind: str) -> None:
    raw = import_bytes(kind, "QA-public-sku", "TWD")
    assert len(raw) < 2 * 1024 * 1024
    if kind == "csv":
        rows = list(csv.reader(io.StringIO(raw.decode())))
    else:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            assert len(archive.namelist()) == 5
            assert all(
                not n.startswith("/") and ".." not in n.split("/") for n in archive.namelist()
            )
            root = ElementTree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
            ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            rows = [
                [c.findtext("s:is/s:t", namespaces=ns) for c in row]
                for row in root.findall("s:sheetData/s:row", ns)
            ]
    assert rows == [
        ["sku", "title", "price", "currency"],
        ["QA-public-sku", "QA synthetic product", "12.500000", "TWD"],
    ]


@pytest.fixture
def validator(tmp_path: Path) -> tuple[Path, Path]:
    # Only public locked tool/dependency bytes from the interpreter's prepared checkout.
    tools_root = Path(sys.executable).parents[2]
    assert (tools_root / "frontend/package-lock.json").read_bytes() == (
        ROOT / "frontend/package-lock.json"
    ).read_bytes()
    node = tools_root / ".tools/node/bin/node"
    assert node.is_file()
    spec = tmp_path / "tests/e2e/v41/validate_response.mjs"
    spec.parent.mkdir(parents=True)
    spec.write_bytes(Path(__file__).with_name("validate_response.mjs").read_bytes())
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_bytes((ROOT / "frontend/package.json").read_bytes())
    (frontend / "node_modules").symlink_to(
        tools_root / "frontend/node_modules", target_is_directory=True
    )
    contract = tmp_path / "docs/v4/v4-1/API_CONTRACT.json"
    contract.parent.mkdir(parents=True)
    contract.write_bytes(
        subprocess.check_output(
            ["git", "show", SCHEMA_SOURCE + ":docs/v4/v4-1/API_CONTRACT.json"], cwd=ROOT
        )
    )
    return node, spec


def lookup() -> dict[str, object]:
    return {
        "schema_version": "v4-business-v1",
        "server_time": "2026-11-04T00:00:00Z",
        "trace_id": str(uuid4()),
        "status": "UNKNOWN",
        "context": {
            "tenant_id": str(uuid4()),
            "organization_id": str(uuid4()),
            "principal_id": str(uuid4()),
            "shop_id": str(uuid4()),
            "reset_epoch": 0,
            "auth_generation": 0,
            "authorized_at": "2026-11-04T00:00:00Z",
        },
        "data": {"request_key": str(uuid4()), "status": "UNKNOWN", "job": None},
    }


def test_real_strict_validator_accepts_minimal_unknown_without_claiming_commit(
    validator: tuple[Path, Path],
) -> None:
    node, spec = validator
    request = {
        "method": "GET",
        "route": "/api/v4/imports/preview-requests/{request_key}",
        "status": 200,
        "payload": lookup(),
    }
    result = subprocess.run(
        [str(node), str(spec)],
        input=json.dumps(request),
        capture_output=True,
        text=True,
        env={},
        timeout=5,
        check=False,
    )
    assert result.returncode == 0 and json.loads(result.stdout) == {"valid": True}


@pytest.mark.parametrize("fault", ["extra", "bool_epoch", "bad_uuid", "redirect", "unlisted_route"])
def test_real_strict_validator_rejects_drift_without_echoing_payload(
    validator: tuple[Path, Path], fault: str
) -> None:
    node, spec = validator
    payload = copy.deepcopy(lookup())
    request = {
        "method": "GET",
        "route": "/api/v4/imports/preview-requests/{request_key}",
        "status": 200,
        "payload": payload,
    }
    if fault == "extra":
        payload["unapproved"] = "private-sentinel"
    elif fault == "bool_epoch":
        payload["context"]["reset_epoch"] = True  # type: ignore[index]
    elif fault == "bad_uuid":
        payload["trace_id"] = "private-sentinel"
    elif fault == "redirect":
        request["status"] = 302
    else:
        request["route"] = "/arbitrary"
    result = subprocess.run(
        [str(node), str(spec)],
        input=json.dumps(request),
        capture_output=True,
        text=True,
        env={},
        timeout=5,
        check=False,
    )
    assert result.returncode in {1, 2} and not json.loads(result.stdout)["valid"]
    assert "private-sentinel" not in result.stdout + result.stderr
