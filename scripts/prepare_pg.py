"""在忽略的 runtime 内生成仅本项目使用的秘密文件，不回显秘密。"""

import argparse
import os
import secrets
from pathlib import Path


def prepare(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name in ("owner_password", "app_password"):
        path = directory / name
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            if not path.is_file() or path.is_symlink() or not path.read_text().strip():
                raise ValueError("invalid existing secret file") from None
            continue
        with os.fdopen(descriptor, "w") as stream:
            stream.write(secrets.token_urlsafe(32))
    print("PG project secret files ready (values withheld)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, default=Path("runtime/pg"))
    prepare(parser.parse_args().directory)


if __name__ == "__main__":
    main()
