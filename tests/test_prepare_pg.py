"""真实临时文件系统上的路径/保留/输出合同；不读取平台配置。"""

import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from pytest import MonkeyPatch as Patch

from scripts import prepare_pg

pytestmark = pytest.mark.offline


def private(tmp_path: Path) -> Path:
    directory = tmp_path.resolve() / "credentials"
    directory.mkdir(mode=0o700)
    return directory


def sentinel(path: Path, *, mode: int = 0o600, content: str = "synthetic-canary") -> None:
    path.write_text(content)
    path.chmod(mode)


def test_fresh_and_repeat_preserves(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    parent = tmp_path.resolve() / "normal-parent"
    parent.mkdir(mode=0o755)
    parent.chmod(0o755)
    directory = parent / "new-parent" / "credentials"
    prepare_pg.prepare(directory)
    assert stat.S_IMODE(directory.lstat().st_mode) == 0o700
    assert directory.lstat().st_uid == os.geteuid()
    before: dict[str, tuple[bytes, int, int]] = {}
    for name in prepare_pg.NAMES:
        path = directory / name
        info = path.lstat()
        assert stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600
        assert info.st_uid == os.geteuid() and info.st_size > 0
        before[name] = (path.read_bytes(), info.st_ino, info.st_mtime_ns)
    prepare_pg.prepare(directory)
    for name, previous in before.items():
        path = directory / name
        assert (path.read_bytes(), path.lstat().st_ino, path.lstat().st_mtime_ns) == previous
    output = capsys.readouterr()
    assert not output.err
    assert all(value[0].decode() not in output.out for value in before.values())
    assert stat.S_IMODE(parent.lstat().st_mode) == 0o755


@pytest.mark.parametrize("kind", ["link", "file", "wide", "foreign"])
def test_directory_rejected_without_changes(
    tmp_path: Path,
    kind: str,
    monkeypatch: Patch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    directory = tmp_path.resolve() / "credentials"
    if kind == "link":
        target = private(tmp_path)
        directory = tmp_path.resolve() / "linked"
        directory.symlink_to(target, target_is_directory=True)
    elif kind == "file":
        sentinel(directory)
    else:
        directory.mkdir(mode=0o700)
        if kind == "wide":
            directory.chmod(0o750)
        else:
            actual = os.geteuid()
            monkeypatch.setattr(os, "geteuid", lambda: actual + 1)
    before = directory.lstat()
    with pytest.raises(prepare_pg.UnsafeCredentialPath, match="unsafe path or metadata"):
        prepare_pg.prepare(directory)
    assert directory.lstat() == before
    if directory.is_dir():
        assert not list(directory.iterdir())
    else:
        assert directory.read_text() == "synthetic-canary"
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("name", prepare_pg.NAMES)
@pytest.mark.parametrize(
    "kind", ["link", "directory", "fifo", "wide", "foreign", "empty", "spaces"]
)
def test_existing_file_preflight_rejects_before_creating_missing(
    tmp_path: Path,
    name: str,
    kind: str,
    monkeypatch: Patch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    directory = private(tmp_path)
    target = directory / name
    canary = "synthetic-" + os.urandom(12).hex()
    outside = tmp_path.resolve() / "outside"
    sentinel(outside, content=canary)
    if kind == "link":
        target.symlink_to(outside)
    elif kind == "directory":
        target.mkdir(mode=0o700)
    elif kind == "fifo":
        os.mkfifo(target, 0o600)
    else:
        sentinel(
            target,
            mode=0o640 if kind == "wide" else 0o600,
            content="" if kind == "empty" else " \n\t" if kind == "spaces" else canary,
        )
    if kind == "foreign":
        original = os.stat

        def foreign(path: Any, *args: Any, **kwargs: Any) -> os.stat_result:
            result = original(path, *args, **kwargs)
            if path == name and kwargs.get("dir_fd") is not None:
                values = list(result)
                values[4] = os.geteuid() + 1
                return os.stat_result(values)
            return result

        monkeypatch.setattr(os, "stat", foreign)
    before = target.lstat()
    with pytest.raises(prepare_pg.UnsafeCredentialPath):
        prepare_pg.prepare(directory)
    assert target.lstat() == before
    assert {entry.name for entry in directory.iterdir()} == {name}
    assert outside.read_text() == canary
    if kind not in {"directory", "fifo"}:
        assert target.read_text() == (
            "" if kind == "empty" else " \n\t" if kind == "spaces" else canary
        )
    assert capsys.readouterr() == ("", "")


def test_existing_good_retained_when_other_invalid(tmp_path: Path) -> None:
    directory = private(tmp_path)
    good, invalid = (directory / name for name in prepare_pg.NAMES)
    sentinel(good)
    sentinel(invalid, mode=0o644)
    before = good.lstat()
    with pytest.raises(prepare_pg.UnsafeCredentialPath):
        prepare_pg.prepare(directory)
    assert good.read_text() == invalid.read_text() == "synthetic-canary"
    assert good.lstat() == before
    assert stat.S_IMODE(invalid.lstat().st_mode) == 0o644


def test_ancestor_symlink_and_parent_hop_rejected(tmp_path: Path) -> None:
    target = tmp_path.resolve() / "target"
    target.mkdir()
    alias = tmp_path.resolve() / "alias"
    alias.symlink_to(target, target_is_directory=True)
    for path in (alias / "credentials", alias / ".." / "credentials"):
        with pytest.raises(prepare_pg.UnsafeCredentialPath):
            prepare_pg.prepare(path)
    assert not list(target.iterdir())
    assert not (tmp_path / "credentials").exists()
    # 信任调用者先选定的canonical真实路径可合法使用，不在脚本内自动resolve。
    prepare_pg.prepare(target.resolve() / "credentials")


def test_existing_file_swapped_to_symlink_before_open(tmp_path: Path, monkeypatch: Patch) -> None:
    directory = private(tmp_path)
    target = directory / "app_password"
    sentinel(target)
    outside = tmp_path.resolve() / "outside"
    sentinel(outside)
    original = os.open

    def replace(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        if path == "app_password" and not flags & os.O_CREAT:
            target.unlink()
            target.symlink_to(outside)
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", replace)
    with pytest.raises(prepare_pg.UnsafeCredentialPath):
        prepare_pg.prepare(directory)
    assert not (directory / "owner_password").exists()
    assert outside.read_text() == "synthetic-canary"
    assert target.is_symlink()


@pytest.mark.parametrize("kind", ["link", "regular"])
def test_create_race_never_follows_or_overwrites(
    tmp_path: Path, monkeypatch: Patch, kind: str
) -> None:
    directory = private(tmp_path)
    outside = tmp_path.resolve() / "outside"
    sentinel(outside)
    original = os.open

    def replace(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        if path == "owner_password" and flags & os.O_CREAT:
            assert flags & os.O_EXCL and flags & os.O_NOFOLLOW
            if kind == "link":
                (directory / "owner_password").symlink_to(outside)
            else:
                sentinel(directory / "owner_password")
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", replace)
    with pytest.raises(prepare_pg.UnsafeCredentialPath):
        prepare_pg.prepare(directory)
    assert outside.read_text() == "synthetic-canary"
    assert not (directory / "app_password").exists()


def test_fstat_metadata_required(tmp_path: Path, monkeypatch: Patch) -> None:
    directory = private(tmp_path)
    sentinel(directory / "app_password")
    original = os.fstat

    def foreign(descriptor: int) -> os.stat_result:
        info = original(descriptor)
        if stat.S_ISREG(info.st_mode):
            values = list(info)
            values[4] = os.geteuid() + 1
            return os.stat_result(values)
        return info

    monkeypatch.setattr(os, "fstat", foreign)
    with pytest.raises(prepare_pg.UnsafeCredentialPath):
        prepare_pg.prepare(directory)
    assert not (directory / "owner_password").exists()
    assert (directory / "app_password").read_text() == "synthetic-canary"


def test_cli_failure_withholds_contents_and_traceback(tmp_path: Path) -> None:
    directory = private(tmp_path)
    canary = "synthetic-" + os.urandom(12).hex()
    sentinel(directory / "app_password", content=canary, mode=0o644)
    result = subprocess.run(
        [sys.executable, "-m", "scripts.prepare_pg", "--directory", str(directory)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert not result.stdout
    assert canary not in result.stderr and str(directory) not in result.stderr
    assert "Traceback" not in result.stderr
    assert result.stderr.strip() == "PG credential preparation failed: unsafe path or metadata"
    assert not (directory / "owner_password").exists()


def test_directory_swap_before_open_rejected(tmp_path: Path, monkeypatch: Patch) -> None:
    directory = private(tmp_path)
    outside = tmp_path.resolve() / "outside"
    outside.mkdir(mode=0o700)
    original = os.open

    def replace(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        if path == "credentials":
            directory.rename(tmp_path.resolve() / "retained")
            directory.symlink_to(outside, target_is_directory=True)
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", replace)
    with pytest.raises(prepare_pg.UnsafeCredentialPath):
        prepare_pg.prepare(directory)
    assert not list(outside.iterdir())
    assert not list((tmp_path / "retained").iterdir())


def test_raw_os_error_withheld(tmp_path: Path) -> None:
    canary = "synthetic-" + os.urandom(12).hex()
    code = """
import os, sys
from pathlib import Path
from scripts.prepare_pg import prepare, UnsafeCredentialPath
def fail(*args, **kwargs):
    raise OSError(sys.argv[1])
os.open = fail
try:
    prepare(Path(sys.argv[2]))
except UnsafeCredentialPath:
    raise SystemExit('PG credential preparation failed: unsafe path or metadata') from None
"""
    result = subprocess.run(
        [sys.executable, "-c", code, canary, str(tmp_path.resolve())],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0 and not result.stdout
    assert canary not in result.stderr and "Traceback" not in result.stderr
    assert result.stderr.strip() == "PG credential preparation failed: unsafe path or metadata"
