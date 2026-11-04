"""M3 runtime boundaries with synthetic metadata and subprocess doubles; no Docker resources."""

import json
import os
import subprocess
import time
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
            "--progress=plain",
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


@pytest.mark.parametrize(
    ("line", "code", "http"),
    [
        ("E: Version '99' for 'gcc' was not found", "APT_PIN_UNAVAILABLE", None),
        (
            "E: Unable to correct problems, you have held broken packages.",
            "DEPENDENCY_CONFLICT",
            None,
        ),
        ("curl: (22) The requested URL returned error: 404", "CURL_HTTP_STATUS", 404),
        ("curl: (6) Could not resolve host: private-invalid-host", "DNS", None),
        ("curl: (60) private credential text", "TLS", None),
        ("/" + "tmp/pgvector.tar.gz: FAILED", "DIGEST", None),
        ("make: *** [target] Error 1", "COMPILE", None),
        ("unrecognized private text", "UNKNOWN", None),
    ],
)
def test_build_log_safe_error_enums(tmp_path: Path, line: str, code: str, http: int | None) -> None:
    path = tmp_path / "raw.log"
    with m3.private_log(path) as stream:
        stream.write(("#5 1.0 M3_IMAGE_STAGE ENTER COMPILE\n#5 2.0 " + line + "\n").encode())
    deadline = time.monotonic() + 5
    result = m3.build_output_facts(
        [m3.read_private_log(path, deadline=deadline)], deadline=deadline
    )
    assert result["observed_error"] == code
    assert result["curl_http_status"] == http
    assert line not in json.dumps(result)


def test_only_executed_marker_lines_count(tmp_path: Path) -> None:
    path = tmp_path / "raw.log"
    with m3.private_log(path) as stream:
        stream.write(
            b"#5 [extension-build 2/2] RUN printf 'M3_IMAGE_STAGE DONE INSTALL'; false\n"
            b"  44 | >>> printf 'M3_IMAGE_STAGE DONE INSTALL';\n"
            b"#5 0.1 M3_IMAGE_STAGE ENTER APT_UPDATE\n"
            b"#5 0.2 M3_IMAGE_STAGE DONE APT_UPDATE\n"
            b"#5 0.3 M3_IMAGE_STAGE ENTER APT_INSTALL\n"
            b"#5 0.4 M3_IMAGE_STAGE DONE FUTURE_UNKNOWN\n"
        )
    deadline = time.monotonic() + 5
    result = m3.build_output_facts(
        [m3.read_private_log(path, deadline=deadline)], deadline=deadline
    )
    assert result["last_entered"] == "APT_INSTALL"
    assert result["last_completed"] == "APT_UPDATE"
    assert result["observed_error"] == "UNKNOWN"


@pytest.mark.parametrize("damage", ["mode", "symlink", "existing"])
def test_private_log_fails_closed(tmp_path: Path, damage: str) -> None:
    path = tmp_path / "raw.log"
    with m3.private_log(path) as stream:
        stream.write(b"private")
    if damage == "existing":
        with pytest.raises(FileExistsError):
            m3.private_log(path)
    else:
        if damage == "mode":
            path.chmod(0o644)
        else:
            path.rename(tmp_path / "target")
            path.symlink_to(tmp_path / "target")
        with pytest.raises((OSError, ValueError)):
            m3.read_private_log(path, deadline=time.monotonic() + 5)


@pytest.mark.parametrize("failure", [None, "build", "source", "inspect", "binding"])
def test_diagnostic_preserves_failure_stage_and_private_logs(
    source: Path, monkeypatch: pytest.MonkeyPatch, failure: str | None
) -> None:
    receipt = binding(source)
    sensitive_text = "PRIVATE_FAKE_CREDENTIAL_NOT_FOR_CONSOLE"

    class Child:
        returncode = 9 if failure == "build" else 0

        def wait(self, timeout: float) -> None:
            assert 0 < timeout <= 300
            if failure == "source":
                (source / m3.INPUTS[0]).write_text("changed")

        def poll(self) -> int:
            return self.returncode

    def spawn(*args: Any, **kwargs: Any) -> Child:
        kwargs["stderr"].write(
            (sensitive_text + "\n#5 1.0 M3_IMAGE_STAGE ENTER APT_INSTALL\n").encode()
        )
        return Child()

    def inspect(_: float) -> dict[str, str]:
        if failure == "inspect":
            raise ValueError(sensitive_text)
        return {key: receipt[key] for key in ("image", "image_id", "architecture")}

    monkeypatch.setattr(subprocess, "Popen", spawn)
    monkeypatch.setattr(m3, "inspect_image", inspect)
    if failure == "binding":
        monkeypatch.setattr(
            m3, "validate_binding", lambda *a: (_ for _ in ()).throw(ValueError(sensitive_text))
        )
    diagnostic: dict[str, Any] = {}
    if failure:
        with pytest.raises(ValueError):
            m3.prepare_image(
                source, datetime.now(UTC) + timedelta(minutes=20), diagnostic=diagnostic
            )
        assert (
            diagnostic["stage"]
            == {
                "build": "BUILD",
                "source": "SOURCE_REVALIDATION",
                "inspect": "INSPECT_METADATA",
                "binding": "BINDING",
            }[failure]
        )
        assert not (source / m3.RECEIPT).exists()
    else:
        m3.prepare_image(source, datetime.now(UTC) + timedelta(minutes=20), diagnostic=diagnostic)
        assert diagnostic["stage"] == "COMPLETE"
        assert diagnostic["code"] == "OK"
    assert diagnostic["reaped"] is True
    assert diagnostic["last_entered"] == "APT_INSTALL"
    assert diagnostic["last_completed"] == "NOT_RUN"
    assert sensitive_text not in json.dumps(diagnostic)
    directory = next((source / ".audit").glob("m3-image-*"))
    assert directory.stat().st_mode & 0o777 == 0o700
    for path in directory.iterdir():
        assert path.stat().st_mode & 0o777 == 0o600
    assert sensitive_text in (directory / "stderr.private.log").read_text()


def test_timeout_records_term_kill_and_reap(source: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    signals: list[int] = []

    class Child:
        pid = 123456789
        returncode: int | None = None
        waits = 0

        def wait(self, timeout: float) -> None:
            self.waits += 1
            if self.waits <= 2:
                raise subprocess.TimeoutExpired("private", timeout)
            self.returncode = -9

        def poll(self) -> int | None:
            return self.returncode

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: Child())
    monkeypatch.setattr(os, "killpg", lambda pid, sig: signals.append(int(sig)))
    diagnostic: dict[str, Any] = {}
    with pytest.raises(subprocess.TimeoutExpired):
        m3.prepare_image(source, datetime.now(UTC) + timedelta(minutes=20), diagnostic=diagnostic)
    assert signals == [15, 9]
    assert diagnostic["timedout"] is True
    assert diagnostic["returncode"] == -9
    assert diagnostic["reaped"] is True
    assert diagnostic["code"] == "BUILD_TIMEOUT"


def test_cli_never_prints_raw_exception_or_build_output(
    source: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sensitive_text = "PRIVATE_FAKE_OUTPUT_AND_EXCEPTION"

    class Child:
        returncode = 7

        def wait(self, timeout: float) -> None:
            pass

        def poll(self) -> int:
            return 7

    def spawn(*args: Any, **kwargs: Any) -> Child:
        kwargs["stdout"].write(sensitive_text.encode())
        kwargs["stderr"].write(sensitive_text.encode())
        return Child()

    monkeypatch.setattr(m3, "ROOT", source)
    monkeypatch.setattr(subprocess, "Popen", spawn)
    monkeypatch.setattr(
        "sys.argv",
        ["image", "--stop-at-utc", (datetime.now(UTC) + timedelta(minutes=20)).isoformat()],
    )
    with pytest.raises(SystemExit) as error:
        m3.main()
    summary = json.loads(str(error.value))
    assert summary["stage"] == "BUILD"
    assert summary["returncode"] == 7
    assert summary["reaped"] is True
    assert sensitive_text not in str(error.value) + str(capsys.readouterr())


def test_dockerfile_markers_preserve_original_commands() -> None:
    import subprocess as process

    original = process.check_output(
        [
            "git",
            "show",
            "cbd5d5464b9e2b4a62463f2ba51d100125326e8c:infrastructure/knowledge_pgvector.Dockerfile",
        ],
        cwd=ROOT,
        text=True,
    )
    current = (ROOT / "infrastructure/knowledge_pgvector.Dockerfile").read_text()
    without_markers = "\n".join(
        line for line in current.splitlines() if "M3_IMAGE_STAGE" not in line
    )
    # The old last command now continues to the final DONE printf; shell statement is identical.
    without_markers = without_markers.replace("builder-packages.txt; \\", "builder-packages.txt")
    assert without_markers.strip() == original.strip()
    for stage in m3.STAGES:
        assert current.count("M3_IMAGE_STAGE ENTER " + stage + "'") == 1
        assert current.count("M3_IMAGE_STAGE DONE " + stage + "'") == 1


@pytest.mark.parametrize("grows_after_stat", [False, True])
def test_private_log_size_limit_checks_stat_and_bounded_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, grows_after_stat: bool
) -> None:
    path = tmp_path / "raw.log"
    with m3.private_log(path) as stream:
        stream.truncate(m3.LOG_LIMIT + 1)
    actual_fstat = os.fstat
    calls = 0

    def fstat(fd: int) -> os.stat_result:
        nonlocal calls
        calls += 1
        result = actual_fstat(fd)
        if grows_after_stat and calls == 1:
            fields = list(result)
            fields[6] = 0
            return os.stat_result(fields)
        return result

    monkeypatch.setattr(os, "fstat", fstat)
    with pytest.raises(m3.LogTooLargeError, match="^LOG_TOO_LARGE$"):
        m3.read_private_log(path, deadline=time.monotonic() + 5)
    assert calls == (2 if grows_after_stat else 1)


def test_log_parser_checks_budget_during_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    ticks = iter([0.0, 0.1, 5.0])
    monkeypatch.setattr(time, "monotonic", lambda: next(ticks))
    with pytest.raises(TimeoutError):
        m3.build_output_facts(
            [b"M3_IMAGE_STAGE ENTER COMPILE\nM3_IMAGE_STAGE DONE COMPILE\n"], deadline=1
        )


@pytest.mark.parametrize("diagnostic_failure", [None, "size", "budget", "parse_budget"])
def test_diagnostic_limits_preserve_build_facts_and_read_once(
    source: Path, monkeypatch: pytest.MonkeyPatch, diagnostic_failure: str | None
) -> None:
    reads: list[str] = []
    clock = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])

    class Child:
        returncode = 9

        def wait(self, timeout: float) -> None:
            if diagnostic_failure == "budget":
                clock[0] = 120

        def poll(self) -> int:
            return 9

    def spawn(*args: Any, **kwargs: Any) -> Child:
        if diagnostic_failure == "size":
            kwargs["stderr"].truncate(m3.LOG_LIMIT + 1)
        else:
            kwargs["stderr"].write(b"M3_IMAGE_STAGE ENTER APT_INSTALL\n")
        return Child()

    actual_read = m3.read_private_log

    def read(path: Path, *, deadline: float) -> bytes:
        reads.append(path.name)
        assert deadline <= 5
        return actual_read(path, deadline=deadline)

    monkeypatch.setattr(subprocess, "Popen", spawn)
    monkeypatch.setattr(m3, "read_private_log", read)
    if diagnostic_failure == "parse_budget":

        def parse(*args: Any, **kwargs: Any) -> dict[str, Any]:
            raise TimeoutError("private unprinted input")

        monkeypatch.setattr(m3, "build_output_facts", parse)
    facts: dict[str, Any] = {}
    with pytest.raises(ValueError, match="M3 bounded image build failed"):
        m3.prepare_image(source, datetime.now(UTC) + timedelta(seconds=190), diagnostic=facts)
    assert facts["stage"] == "BUILD"
    assert facts["code"] == "BUILD_NONZERO"
    assert facts["returncode"] == 9
    assert facts["timedout"] is False
    assert facts["reaped"] is True
    assert facts["source_commit"] == "a" * 40
    assert len(facts["inputs"]) == 6
    assert reads == (
        [] if diagnostic_failure == "budget" else ["stdout.private.log", "stderr.private.log"]
    )
    if diagnostic_failure is None:
        assert facts["diagnostic_code"] == "OK"
        assert facts["last_entered"] == "APT_INSTALL"
        assert len(facts["logs_sha256"]) == 2
    else:
        assert facts["diagnostic_code"] == (
            "LOG_TOO_LARGE" if diagnostic_failure == "size" else "BUDGET_EXHAUSTED"
        )
        assert facts["diagnostic_stage"] == "UNKNOWN"
        assert facts["last_entered"] == facts["last_completed"] == "UNKNOWN"
        assert "logs_sha256" not in facts
    assert not (source / m3.RECEIPT).exists()
