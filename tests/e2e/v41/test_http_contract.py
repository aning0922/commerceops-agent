"""Actual Ajv against accepted schema + synthetic public files, no HTTP or PG."""

import copy
import csv
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from defusedxml import ElementTree  # type: ignore[import-untyped]

from .http_recipes import assert_import_receipt, confirmation_fields, import_bytes
from .process import ROOT

pytestmark = pytest.mark.offline
SCHEMA_SOURCE = "8cb673e5c38e98ce21fb1bb1d8b8d20fe5cdc181"


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


@pytest.mark.parametrize(
    "saved,preview,current",
    [("saved", "saved", "new"), ("saved", "new", "new"), ("new", "saved", "new")],
)
def test_confirmation_requires_all_three_revisions(saved: str, preview: str, current: str) -> None:
    job = {
        "data_revision": saved,
        "version": 1,
        "job_digest": "public-digest",
        "parser_version": "v41-parser-1",
        "import_schema_version": "v41-import-1",
    }
    with pytest.raises(ValueError, match="REPREVIEW_REQUIRED"):
        confirmation_fields(job, preview, current)


def test_confirmation_preserves_original_job_binding() -> None:
    job = {
        "data_revision": "same",
        "version": 2,
        "job_digest": "original-digest",
        "parser_version": "v41-parser-1",
        "import_schema_version": "v41-import-1",
    }
    assert confirmation_fields(job, "same", "same") == {
        "expected_job_version": 2,
        "expected_job_digest": "original-digest",
    }
    job["parser_version"] = "unexpected"
    with pytest.raises(ValueError, match="PARSER_SCHEMA"):
        confirmation_fields(job, "same", "same")


@pytest.mark.parametrize("missing", ["data_revision", "parser_version"])
def test_latest_job_ref_strict_schema_rejects_missing_revision_or_wrong_parser(
    validator: tuple[Path, Path], missing: str
) -> None:
    node, spec = validator
    payload = lookup()
    payload["status"] = "OK"
    data = payload["data"]
    assert isinstance(data, dict)
    data["status"] = "COMMITTED"
    job = {
        "import_job_id": str(uuid4()),
        "version": 1,
        "parent_job_id": None,
        "job_digest": "a" * 64,
        "data_revision": "b" * 64,
        "parser_version": "v41-parser-1",
        "import_schema_version": "v41-import-1",
        "expires_at": "2026-11-04T00:10:00Z",
    }
    if missing == "data_revision":
        del job["data_revision"]
    else:
        job["parser_version"] = "wrong"
    data["job"] = job
    request = {
        "method": "GET",
        "route": "/api/v4/imports/preview-requests/{request_key}",
        "status": 200,
        "payload": payload,
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
    assert result.returncode == 1 and json.loads(result.stdout) == {"valid": False}


def test_import_receipt_binds_job_version_without_artificial_increment() -> None:
    job = {"import_job_id": str(uuid4()), "version": 2, "data_revision": "before"}
    key = str(uuid4())
    receipt = {
        "operation": "import_confirm",
        "request_key": key,
        "resource_id": job["import_job_id"],
        "resource_version": 2,
        "before_revision": "before",
        "after_revision": "after",
    }
    assert_import_receipt(receipt, job, key, "after")
    changes: list[dict[str, Any]] = [
        {"resource_version": 3},
        {"resource_id": str(uuid4())},
        {"before_revision": "wrong"},
        {"request_key": str(uuid4())},
    ]
    for change in changes:
        with pytest.raises(AssertionError):
            assert_import_receipt({**receipt, **change}, job, key, "after")
