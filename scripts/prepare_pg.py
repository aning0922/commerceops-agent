"""准备私有 PG 凭据；路径只用 no-follow 描述符，不回显秘密或原异常。"""

import argparse
import os
import secrets
import stat
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path

NAMES = ("owner_password", "app_password")


class UnsafeCredentialPath(ValueError):
    """固定安全错误；不含路径、内容或底层异常。"""


def _reject() -> None:
    raise UnsafeCredentialPath("PG credential preparation failed: unsafe path or metadata")


def _private(info: os.stat_result, *, directory: bool) -> None:
    expected = 0o700 if directory else 0o600
    valid_type = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if not valid_type or stat.S_IMODE(info.st_mode) != expected or info.st_uid != os.geteuid():
        _reject()


def _same(left: os.stat_result, right: os.stat_result) -> None:
    if (left.st_dev, left.st_ino) != (right.st_dev, right.st_ino):
        _reject()


@contextmanager
def _directory(directory: Path) -> Iterator[int]:
    # 不自行 resolve 用户路径中的 symlink；调用者须传可信 canonical 路径。
    if ".." in directory.parts:
        _reject()
    absolute = Path(os.path.abspath(directory))
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    with ExitStack() as stack:
        current = os.open(absolute.anchor, flags)
        stack.callback(os.close, current)
        _same(os.lstat(absolute.anchor), os.fstat(current))
        if len(absolute.parts) < 2:
            _reject()
        for position, name in enumerate(absolute.parts[1:], start=1):
            created = False
            try:
                observed = os.stat(name, dir_fd=current, follow_symlinks=False)
            except FileNotFoundError:
                os.mkdir(name, mode=0o700, dir_fd=current)
                created = True
                observed = os.stat(name, dir_fd=current, follow_symlinks=False)
            if not stat.S_ISDIR(observed.st_mode):
                _reject()
            final = position == len(absolute.parts) - 1
            if final or created:
                _private(observed, directory=True)
            child = os.open(name, flags, dir_fd=current)
            stack.callback(os.close, child)
            opened = os.fstat(child)
            _same(observed, opened)
            if final or created:
                _private(opened, directory=True)
            if final:
                yield child
                _private(os.fstat(child), directory=True)
                final_info = os.stat(name, dir_fd=current, follow_symlinks=False)
                _same(final_info, os.fstat(child))
                _private(final_info, directory=True)
                return
            current = child


def _existing(directory: int, name: str) -> os.stat_result | None:
    try:
        before = os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        return None
    _private(before, directory=False)
    # NONBLOCK 防止普通文件被并发换成 FIFO 后读取阻塞；fstat 先于读取。
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
        opened = os.fstat(stream.fileno())
        _same(before, opened)
        _private(opened, directory=False)
        if not stream.read().strip():
            _reject()
        after = os.fstat(stream.fileno())
        _private(after, directory=False)
        if after.st_size == 0:
            _reject()
        bound = os.stat(name, dir_fd=directory, follow_symlinks=False)
        _same(after, bound)
        _private(bound, directory=False)
        return after


def _binding(directory: int, name: str, previous: os.stat_result) -> None:
    current = os.stat(name, dir_fd=directory, follow_symlinks=False)
    _same(previous, current)
    _private(current, directory=False)
    if current.st_size == 0:
        _reject()


def prepare(directory: Path) -> None:
    try:
        # 支持 macOS/Linux POSIX；不退化为 follow-symlink 或仅 Path.is_file 检查。
        if os.name != "posix" or not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
            _reject()
        with _directory(directory) as descriptor:
            existing = {name: _existing(descriptor, name) for name in NAMES}
            # 所有现存文件检查成功才创建任何缺项；不 chmod 修复未知路径。
            verified = {name: info for name, info in existing.items() if info is not None}
            for name, info in existing.items():
                if info is not None:
                    continue
                _private(os.fstat(descriptor), directory=True)
                for known, previous in verified.items():
                    _binding(descriptor, known, previous)
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                created = os.open(name, flags, 0o600, dir_fd=descriptor)
                with os.fdopen(created, "w", encoding="utf-8") as stream:
                    _private(os.fstat(stream.fileno()), directory=False)
                    stream.write(secrets.token_urlsafe(32))
                    stream.flush()
                    info = os.fstat(stream.fileno())
                    _private(info, directory=False)
                    verified[name] = info
            for name, previous in verified.items():
                _binding(descriptor, name, previous)
    except (OSError, ValueError):
        raise UnsafeCredentialPath(
            "PG credential preparation failed: unsafe path or metadata"
        ) from None
    print("PG project secret files ready (values withheld)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, default=Path("runtime/pg"))
    try:
        prepare(parser.parse_args().directory)
    except UnsafeCredentialPath:
        raise SystemExit("PG credential preparation failed: unsafe path or metadata") from None


if __name__ == "__main__":
    main()
