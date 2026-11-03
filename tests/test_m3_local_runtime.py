"""M3 runtime boundaries with synthetic metadata and subprocess doubles; no Docker resources."""

import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

from scripts import m2_owned
from scripts import m3_pgvector as m3

pytestmark = pytest.mark.offline
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for name in m3.INPUTS:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("public synthetic input\n")
    monkeypatch.setattr(
        m3,
        "source_identity",
        lambda _, timeout=5: {
            "source_commit": "a" * 40,
            "source_tree": "b" * 40,
        },
    )
    return tmp_path


def binding(root: Path) -> dict[str, Any]:
    return {
        "image": m3.IMAGE,
        "image_id": "sha256:" + "c" * 64,
        "architecture": "arm64",
        "inputs": m3.source_hashes(root),
        **m3.source_identity(root),
    }


def metadata() -> list[dict[str, Any]]:
    return [
        {
            "Id": "sha256:" + "c" * 64,
            "RepoTags": [m3.IMAGE],
            "Os": "linux",
            "Architecture": "arm64",
            "Config": {
                "Env": ["PG_MAJOR=17", "PG_VERSION=17.11-1.pgdg12+2"],
                "Labels": {
                    "commerceops.pgvector.version": "0.8.7",
                    "commerceops.pgvector.commit": "f37c13f68b57d2c3472b2214fbcff699d6d34876",
                },
            },
        }
    ]


@pytest.mark.parametrize("damage", [None, "arch", "tag", "pg", "vector", "source", "id", "shape"])
def test_image_metadata_rejects_wrong_runtime_without_output(damage: str | None) -> None:
    data = metadata()
    if damage == "arch":
        data[0]["Architecture"] = "amd64"
    if damage == "tag":
        data[0]["RepoTags"] = [m2_owned.PG_IMAGE]
    if damage == "pg":
        data[0]["Config"]["Env"] = ["PG_MAJOR=17", "PG_VERSION=17.10"]
    if damage == "vector":
        data[0]["Config"]["Labels"]["commerceops.pgvector.version"] = "0.8.6"
    if damage == "source":
        data[0]["Config"]["Labels"]["commerceops.pgvector.commit"] = "d" * 40
    if damage == "id":
        data[0]["Id"] = "not-an-image-id"
    if damage == "shape":
        data[0]["Config"] = None
    if damage:
        with pytest.raises(ValueError):
            m3.image_metadata(data, "arm64")
    else:
        assert m3.image_metadata(data, "arm64")["image"] == m3.IMAGE
        with pytest.raises(ValueError):
            m3.image_metadata(data, "unsupported")


@pytest.mark.parametrize(
    "damage", [None, "input", "source", "image", "project", "service", "files", "workdir"]
)
def test_actual_container_binds_image_source_and_exact_compose_order(
    source: Path, damage: str | None
) -> None:
    receipt = binding(source)
    overlay = source / "private/port.json"
    info: dict[str, Any] = {
        "Image": receipt["image_id"],
        "Config": {
            "Image": m3.IMAGE,
            "Labels": {
                "com.docker.compose.project": "synthetic-owned",
                "com.docker.compose.service": "postgres",
                "com.docker.compose.project.working_dir": str(source),
                "com.docker.compose.project.config_files": ",".join(
                    m3.compose_files(source, True, overlay)
                ),
            },
        },
    }
    if damage == "input":
        (source / m3.INPUTS[1]).write_text("changed\n")
    if damage == "source":
        receipt["source_commit"] = "e" * 40
    if damage == "image":
        info["Image"] = "sha256:" + "f" * 64
    labels = info["Config"]["Labels"]
    for key in ("project", "service", "files", "workdir"):
        if damage == key:
            field = {"files": "config_files", "workdir": "working_dir"}.get(key, key)
            labels[
                "com.docker.compose.project." + field
                if key in {"files", "workdir"}
                else "com.docker.compose." + field
            ] = "foreign"
    if damage:
        with pytest.raises(ValueError):
            m3.validate_container(source, info, receipt, "synthetic-owned", overlay)
    else:
        m3.validate_container(source, info, receipt, "synthetic-owned", overlay)


def test_default_m2_overlay_and_m3_selection_are_disjoint() -> None:
    stock = yaml.safe_load((ROOT / "compose.yml").read_text())
    override = yaml.safe_load((ROOT / "compose.m3.yml").read_text())
    assert stock["services"]["postgres"]["image"] == m2_owned.PG_IMAGE
    assert "build" not in stock["services"]["postgres"]
    assert set(override) == {"services"} and set(override["services"]) == {"postgres"}
    assert set(override["services"]["postgres"]) == {"image", "build"}
    assert override["services"]["postgres"]["image"] == m3.IMAGE != m2_owned.PG_IMAGE
    assert override["services"]["postgres"]["build"] == {
        "context": ".",
        "dockerfile": "infrastructure/knowledge_pgvector.Dockerfile",
    }
    assert m3.compose_flags(ROOT, False) == ["-f", str(ROOT / "compose.yml")]
    assert m3.up_flags(False) == []
    assert m3.up_flags(True) == ["--no-build", "--pull", "never"]
    assert m3.compose_files(ROOT, True)[-1] == str(ROOT / "compose.m3.yml")


@pytest.mark.parametrize("damage", [None, "mode", "symlink", "tag", "missing", "source"])
def test_prepared_receipt_requires_owned_current_source_image(
    source: Path,
    monkeypatch: pytest.MonkeyPatch,
    damage: str | None,
) -> None:
    receipt = binding(source)
    path = source / m3.RECEIPT
    path.parent.mkdir()
    path.write_text(json.dumps(receipt))
    path.chmod(0o600)
    if damage == "mode":
        path.chmod(0o644)
    if damage == "symlink":
        target = path.with_suffix(".other")
        path.rename(target)
        path.symlink_to(target)
    if damage == "source":
        (source / m3.INPUTS[1]).write_text("changed\n")
    actual = {key: receipt[key] for key in ("image", "image_id", "architecture")}
    if damage == "tag":
        actual["image_id"] = "sha256:" + "d" * 64

    def inspect(timeout: float) -> dict[str, str]:
        assert 0 < timeout <= 5
        if damage == "missing":
            raise ValueError("M3 prepared image missing")
        return actual

    monkeypatch.setattr(m3, "inspect_image", inspect)
    if damage:
        with pytest.raises(ValueError):
            m3.prepared_image(source, 5)
    else:
        assert m3.prepared_image(source, 5) == receipt


def test_expired_image_preparation_cannot_spawn(
    source: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: pytest.fail("unexpected build"))
    with pytest.raises(ValueError):
        m3.prepare_image(source, datetime.now(UTC) + timedelta(seconds=84))


def test_bounded_preparation_records_only_exact_source_and_image(
    source: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = binding(source)
    calls: list[list[str]] = []

    class Child:
        returncode = 0

        def wait(self, timeout: float) -> None:
            assert 0 < timeout <= 300

        def poll(self) -> int:
            return 0

    def spawn(command: list[str], **kwargs: Any) -> Child:
        calls.append(command)
        assert kwargs["start_new_session"] is True
        return Child()

    monkeypatch.setattr(subprocess, "Popen", spawn)
    monkeypatch.setattr(
        m3,
        "inspect_image",
        lambda _: {key: receipt[key] for key in ("image", "image_id", "architecture")},
    )
    m3.prepare_image(source, datetime.now(UTC) + timedelta(minutes=20))
    assert calls == [
        [
            "docker",
            "build",
            "-f",
            str(source / "infrastructure/knowledge_pgvector.Dockerfile"),
            "-t",
            m3.IMAGE,
            str(source),
        ]
    ]
    assert json.loads((source / m3.RECEIPT).read_text()) == receipt
    assert (source / m3.RECEIPT).stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError):
        m3.prepare_image(source, datetime.now(UTC) + timedelta(minutes=20))
    assert len(calls) == 1


def test_current_ci_consumers_all_require_m3_and_bounded_preparation() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/quality.yml").read_text())
    jobs = workflow["jobs"]
    assert set(jobs) == {"quality", "phase3", "frontend", "n01-web", "pg-pair"}
    for name in ("quality", "phase3", "frontend", "n01-web"):
        steps = jobs[name]["steps"]
        build = [s for s in steps if "python -m scripts.m3_pgvector" in s.get("run", "")]
        assert len(build) == 1 and "--stop-at-utc" in build[0]["run"]
        run = [
            s
            for s in steps
            if any(
                module in s.get("run", "")
                for module in (
                    "python -m scripts.pg_diagnostic",
                    "python -m tests.e2e.web.run_c09_n01",
                    "python -m tests.e2e.web.run_live_batches",
                )
            )
        ]
        assert len(run) == 1 and "--m3-pgvector" in run[0]["run"]
        assert steps.index(build[0]) < steps.index(run[0])
        if name in {"frontend", "n01-web"}:
            gates = [s for s in steps if s.get("name", "").startswith("Require source-bound M3")]
            assert len(gates) == 1 and 'window["m3_pgvector"]' in gates[0]["run"]
            assert "if" not in gates[0] and "continue-on-error" not in gates[0]


def test_build_timeout_reaps_only_owned_cli_and_never_writes_success(
    source: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signals: list[tuple[int, int]] = []

    class Child:
        pid = 123456789
        returncode: int | None = None
        waits = 0

        def wait(self, timeout: float) -> None:
            self.waits += 1
            if self.waits == 1:
                raise subprocess.TimeoutExpired("synthetic build", timeout)
            self.returncode = -15

        def poll(self) -> int | None:
            return self.returncode

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: Child())
    monkeypatch.setattr(os, "killpg", lambda pid, sig: signals.append((pid, sig)))
    with pytest.raises(subprocess.TimeoutExpired):
        m3.prepare_image(source, datetime.now(UTC) + timedelta(minutes=20))
    assert signals == [(123456789, 15)]
    assert not (source / m3.RECEIPT).exists()


def test_source_input_symlink_is_refused_before_build(
    source: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = source / "compose.m3.yml"
    target = path.with_suffix(".other")
    path.rename(target)
    path.symlink_to(target)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: pytest.fail("unexpected build"))
    with pytest.raises(ValueError, match="symlink refused"):
        m3.prepare_image(source, datetime.now(UTC) + timedelta(minutes=20))
