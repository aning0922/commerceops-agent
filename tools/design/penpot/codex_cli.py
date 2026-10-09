"""为一次 Codex CLI 启动加载私有 Penpot 配置；不修改全局配置。"""

import argparse
import json
import os
import re
import shutil
import tomllib
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    config = tomllib.loads((args.runtime / ".codex/config.toml").read_text())
    server = config["mcp_servers"]["penpot"]
    url = server["url"]
    if not url.startswith("http://localhost:19001/mcp/stream?userToken="):
        raise ValueError("仅允许专用本机设计实例")
    overrides = [
        "mcp_servers.penpot.url=" + json.dumps(url),
        "mcp_servers.penpot.required=true",
        "mcp_servers.penpot.startup_timeout_sec=20",
        "mcp_servers.penpot.tool_timeout_sec=60",
        'mcp_servers.penpot.enabled_tools=["high_level_overview","penpot_api_info",'
        '"execute_code","export_shape"]',
        'mcp_servers.penpot.default_tools_approval_mode="approve"',
    ]
    # 仅禁用用户配置里已具有 transport 的服务器，不能给插件派生的条目
    # 单独添加 enabled=false（该 CLI 会报 invalid transport）。
    user_config = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "config.toml"
    if user_config.exists():
        user_servers = tomllib.loads(user_config.read_text()).get("mcp_servers", {})
        for name, settings in user_servers.items():
            if (
                name != "penpot"
                and re.fullmatch(r"[A-Za-z0-9_-]+", name)
                and ("url" in settings or "command" in settings)
            ):
                overrides.append("mcp_servers." + name + ".enabled=false")
    executable = shutil.which("codex")
    if executable is None:
        raise RuntimeError("Codex CLI 不可用")
    command = [executable]
    for override in overrides:
        command.extend(["-c", override])
    forwarded = args.arguments
    if forwarded and forwarded[0] == "--":
        forwarded = forwarded[1:]
    os.chdir(args.runtime)
    os.execv(executable, command + forwarded)  # noqa: S606 - resolved Codex only; no shell


if __name__ == "__main__":
    main()
