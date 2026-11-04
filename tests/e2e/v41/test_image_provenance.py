"""Public file/receipt and actual local read-program tests; never Docker execution."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from .image_provenance import READ_PUBLIC, probe_argv, validate_build, validate_measured

pytestmark = pytest.mark.offline


def test_same_id_without_same_source_and_actual_bytes_never_accepts() -> None:
    source = "a" * 40
    tree = "b" * 40
    image = "sha256:" + "c" * 64
    files = {"backend/public.py": "d" * 64}
    receipt = {
        "source_sha": source,
        "source_tree": tree,
        "test_image_id": image,
        "test_build_native_exit": 0,
        "runtime_files_sha256": files,
    }
    validate_build(receipt, source, tree, image, files)
    for bad in [
        {**receipt, "source_sha": "e" * 40},
        {**receipt, "runtime_files_sha256": {}},
        {**receipt, "test_build_native_exit": False},
    ]:
        with pytest.raises(ValueError):
            validate_build(bad, source, tree, image, files)
    assert validate_measured(json.dumps(files).encode(), files)["files"] == 1
    with pytest.raises(ValueError):
        validate_measured(json.dumps({"backend/public.py": "e" * 64}).encode(), files)


def test_fixed_public_read_program_measures_real_bytes(tmp_path: Path) -> None:
    root = tmp_path / "app"
    root.mkdir()
    (root / "public.py").write_text("public fixture\n")
    # Substitute only /app for an isolated local filesystem test, not the program logic.
    code = READ_PUBLIC.replace("pathlib.Path('/app')", "pathlib.Path(" + repr(str(root)) + ")")
    native = subprocess.run(
        [sys.executable, "-c", code],
        input=json.dumps(["public.py"]).encode(),
        capture_output=True,
        timeout=3,
        check=False,
    )
    expected = {"public.py": hashlib.sha256((root / "public.py").read_bytes()).hexdigest()}
    assert native.returncode == 0 and validate_measured(native.stdout, expected)["files"] == 1
    refused = subprocess.run(
        [sys.executable, "-c", code],
        input=json.dumps(["../outside"]).encode(),
        capture_output=True,
        timeout=3,
        check=False,
    )
    assert refused.returncode != 0


def test_image_probe_is_explicit_networkless_and_has_no_host_mount(tmp_path: Path) -> None:
    argv = probe_argv(
        "/usr/local/bin/docker", "v41qa_probe_fixture01", "sha256:" + "a" * 64, tmp_path, 501
    )
    assert argv[argv.index("--network") + 1] == "none"
    assert "--read-only" in argv and "--cap-drop" in argv and "--rm" in argv
    assert not {"-v", "--volume", "--mount", "--env-file", "--privileged"} & set(argv)
