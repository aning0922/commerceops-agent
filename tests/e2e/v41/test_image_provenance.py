"""Public file/receipt and actual local read-program tests; never Docker execution."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from .image_provenance import READ_PUBLIC, probe_argv, validate_build, validate_measured
from .test_owner_setup import build_fixture

pytestmark = pytest.mark.offline


def test_same_id_without_same_source_and_actual_bytes_never_accepts() -> None:
    source = "a" * 40
    tree = "b" * 40
    image = "sha256:" + "c" * 64
    files = {"backend/src/commerceops/__init__.py": "d" * 64}
    receipt, raw = build_fixture(files, source, tree, image)
    validate_build(receipt, source, tree, image, files, raw)
    for bad in [
        {**receipt, "status": "COPIED_BYTES_ONLY"},
        {**receipt, "image": {"id": "sha256:" + "e" * 64}},
        {**receipt, "source_binding": {**receipt["source_binding"], "source": "e" * 40}},
    ]:
        with pytest.raises(ValueError):
            validate_build(bad, source, tree, image, files, raw)
    assert (
        validate_measured(json.dumps(receipt["inside_verification"]).encode(), files)[
            "runtime_files"
        ]
        == 1
    )
    with pytest.raises(ValueError):
        validate_measured(json.dumps({"status": "COPIED_BYTES_ONLY"}).encode(), files)


def test_fixed_public_read_program_measures_real_bytes(tmp_path: Path) -> None:
    root = tmp_path / "app"
    expected = {}
    for name in (
        "backend/src/commerceops/__init__.py",
        "backend/src/commerceops/public.py",
        "tests/public.txt",
        "scripts/public.txt",
        "pyproject.toml",
        "uv.lock",
        ".python-version",
    ):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('"""Public fixture."""\n')
        expected[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    site = root / ".venv/lib/python3.12/site-packages"
    package = site / "commerceops"
    package.mkdir(parents=True)
    for name in ("__init__.py", "public.py"):
        (package / name).write_bytes((root / "backend/src/commerceops" / name).read_bytes())
    # Relocate only the two fixed filesystem anchors for an isolated protocol test.
    # The actual copied/installed enumeration and byte comparison remain the approved program.
    code = (
        "import sys;sys.path.insert(0,"
        + repr(str(site))
        + ");\n"
        + READ_PUBLIC.replace(
            "pathlib.Path('/app')", "pathlib.Path(" + repr(str(root)) + ")"
        ).replace("'/app/.venv'", repr(str(root / ".venv")))
    )

    def run() -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [sys.executable, "-I", "-B", "-c", code],
            input=json.dumps(expected).encode(),
            capture_output=True,
            timeout=3,
            check=False,
        )

    native = run()
    assert native.returncode == 0
    assert validate_measured(native.stdout, expected)["installed_python_files"] == 2
    (package / "public.py").write_text("changed installed bytes")
    refused = run()
    assert refused.returncode != 0 and not refused.stdout


def test_image_probe_is_explicit_networkless_and_has_no_host_mount(tmp_path: Path) -> None:
    argv = probe_argv(
        "/usr/local/bin/docker", "v41qa_probe_fixture01", "sha256:" + "a" * 64, tmp_path, 501
    )
    assert argv[argv.index("--network") + 1] == "none"
    assert "--read-only" in argv and "--cap-drop" in argv and "--rm" in argv
    assert not {"-v", "--volume", "--mount", "--env-file", "--privileged"} & set(argv)
