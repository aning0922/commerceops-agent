"""当前可提交文件集合，不扫描已忽略的本地运行目录与秘密配置。"""

import subprocess
from pathlib import Path


def versionable_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        capture_output=True,
        check=True,
    )
    return sorted({Path(p.decode()) for p in result.stdout.split(b"\0") if p})


def indexed_files(root: Path) -> list[tuple[str, str, Path]]:
    """读取 index 对象；不能假定已暂存内容等于工作区。"""
    result = subprocess.run(
        ["git", "ls-files", "--stage", "-z"],
        cwd=root,
        capture_output=True,
        check=True,
    )
    files = []
    for entry in result.stdout.split(b"\0"):
        if not entry:
            continue
        metadata, _, filename = entry.partition(b"\t")
        mode, oid, stage = metadata.decode().split()
        if stage != "0":
            raise ValueError("index conflicts")
        files.append((mode, oid, Path(filename.decode())))
    return files
