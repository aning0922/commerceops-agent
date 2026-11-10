"""Real local stand-in executables test argv/env only; no Docker or socket connection."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from .fixed_daemon import file_hash, freeze, load

pytestmark = pytest.mark.offline


def tools(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    tool = tmp_path / "public-docker"
    tool.write_text(
        "#!" + sys.executable + "\nimport json,os,sys,pathlib\n"
        "with pathlib.Path(__file__).with_suffix('.calls').open('a') as log:"
        "log.write(json.dumps(sys.argv[1:])+'\\n')\n"
        "print(json.dumps({'argv':sys.argv[1:],'environment':dict(os.environ)}))\n"
    )
    tool.chmod(0o700)
    plugin = tmp_path / "docker-compose"
    plugin.write_text("public plugin fixture")
    plugin.chmod(0o700)
    receipt = {
        "docker_endpoint": "unix:///approved/local.sock",
        "docker_binary_sha256": file_hash(tool),
        "docker_server_id": "approved-server",
        "compose_plugin_path": str(plugin),
        "compose_plugin_sha256": file_hash(plugin),
    }
    return tool, plugin, receipt


def test_wrong_tool_or_endpoint_has_zero_commands(tmp_path: Path) -> None:
    tool, _, receipt = tools(tmp_path)
    for change in [{"docker_endpoint": "tcp://other"}, {"docker_binary_sha256": "wrong"}]:
        directory = tmp_path / str(len(list(tmp_path.iterdir())))
        directory.mkdir(mode=0o700)
        with pytest.raises(ValueError):
            freeze(directory, str(tool), {**receipt, **change})
        assert not (directory / "docker-fixed").exists()
        assert not (directory / "docker-home").exists()


def test_all_calls_ignore_implicit_context_credentials_and_refuse_override(tmp_path: Path) -> None:
    tool, _, receipt = tools(tmp_path)
    directory = tmp_path / "new-case"
    directory.mkdir(mode=0o700)
    shim = freeze(directory, str(tool), receipt)
    assert load(directory) == shim
    result = subprocess.run(
        [str(shim), "image", "inspect", "public-id"],
        capture_output=True,
        text=True,
        env={
            "HOME": "/never-read-old-home",
            "DOCKER_CONTEXT": "wrong-implicit",
            "DOCKER_HOST": "tcp://wrong",
            "DOCKER_CONFIG": "/never-read-old-credentials",
        },
        timeout=3,
        check=False,
    )
    assert result.returncode == 0
    value = json.loads(result.stdout)
    assert value["argv"][:2] == ["--host", "unix:///approved/local.sock"]
    assert value["environment"]["HOME"] == str(directory / "docker-home")
    assert value["environment"]["DOCKER_CONFIG"] == str(directory / "docker-config")
    assert "DOCKER_CONTEXT" not in value["environment"]
    assert value["environment"]["DOCKER_HOST"] == receipt["docker_endpoint"]
    refused = subprocess.run(
        [str(shim), "--context", "other", "ps"], capture_output=True, env={}, timeout=3, check=False
    )
    assert refused.returncode != 0 and not refused.stdout
    assert json.loads((directory / "docker-config/config.json").read_text())["auths"] == {}
    assert (directory / "docker-config/config.json").stat().st_mode & 0o777 == 0o600
    assert os.path.isabs(str(shim))
