"""下载官方固定版本到项目 .tools，按入库 SHA256 校验，不改全局 PATH。"""

import hashlib
import json
import platform
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    machine = {"aarch64": "arm64", "arm64": "arm64", "x86_64": "x64"}.get(platform.machine())
    target = f"{platform.system().lower()}-{machine}"
    versions = json.loads((ROOT / "scripts/tool_versions.json").read_text())
    tools = ROOT / ".tools"
    tools.mkdir(exist_ok=True)
    for name, spec in versions.items():
        if target not in spec["checksums"]:
            raise SystemExit(f"不支持的工具链平台：{target}")
        version = spec["version"]
        if name == "node":
            archive = f"node-v{version}-{target}.tar.gz"
            url = f"https://nodejs.org/dist/v{version}/{archive}"
            destination = tools / "node"
        else:
            archive = f"gitleaks_{version}_{target.replace('-', '_')}.tar.gz"
            url = f"https://github.com/gitleaks/gitleaks/releases/download/v{version}/{archive}"
            destination = tools / "gitleaks"
        with tempfile.TemporaryDirectory(dir=tools) as temp:
            staging = Path(temp)
            blob = staging / archive
            with urllib.request.urlopen(url, timeout=60) as response, blob.open("wb") as out:  # noqa: S310 - fixed official HTTPS
                shutil.copyfileobj(response, out)
            if hashlib.sha256(blob.read_bytes()).hexdigest() != spec["checksums"][target]:
                raise SystemExit(f"{name}: SHA256 不匹配，拒绝安装")
            with tarfile.open(blob) as package:
                package.extractall(staging / "unpacked", filter="data")
            if name == "node":
                installed = staging / "unpacked" / archive.removesuffix(".tar.gz")
                if destination.exists():
                    shutil.rmtree(destination)
                shutil.move(installed, destination)
            else:
                shutil.copy2(staging / "unpacked/gitleaks", destination)
                destination.chmod(0o755)
        print(f"{name} {version}: {target} 下载与 SHA256 校验完成")


if __name__ == "__main__":
    main()
