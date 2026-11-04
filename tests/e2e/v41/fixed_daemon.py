"""Dedicated local Docker selection shared by every helper/adapter/cleanup call."""

import hashlib
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from tests.e2e.v4.owned_driver import private


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze(directory: Path, docker: str, receipt: dict[str, Any]) -> Path:
    tool = Path(docker).resolve(strict=True)
    endpoint = receipt.get("docker_endpoint", "")
    url = urlsplit(endpoint)
    if (
        url.scheme != "unix"
        or url.netloc
        or not url.path.startswith("/")
        or url.query
        or url.fragment
    ):
        raise ValueError("ROOT_EXPLICIT_LOCAL_UNIX_DAEMON_REQUIRED")
    if file_hash(tool) != receipt.get("docker_binary_sha256") or not receipt.get(
        "docker_server_id"
    ):
        raise ValueError("ROOT_DOCKER_TOOL_SERVER_PIN_REQUIRED")
    plugin = Path(receipt.get("compose_plugin_path", ""))
    if (
        not plugin.is_absolute()
        or not plugin.is_file()
        or file_hash(plugin) != receipt.get("compose_plugin_sha256")
    ):
        raise ValueError("ROOT_PUBLIC_COMPOSE_PLUGIN_PIN_REQUIRED")
    home = directory / "docker-home"
    config = directory / "docker-config"
    home.mkdir(mode=0o700)
    config.mkdir(mode=0o700)
    plugins = config / "cli-plugins"
    plugins.mkdir(mode=0o700)
    (plugins / "docker-compose").symlink_to(plugin.resolve())
    private(config / "config.json", json.dumps({"auths": {}}))
    environment = {
        "PATH": "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin",
        "HOME": str(home),
        "DOCKER_CONFIG": str(config),
        "DOCKER_HOST": endpoint,
    }
    pins = {
        str(Path(sys.executable).resolve()): file_hash(Path(sys.executable).resolve()),
        str(tool): file_hash(tool),
        str(plugin.resolve()): file_hash(plugin),
        str(config / "config.json"): file_hash(config / "config.json"),
    }
    shim = directory / "docker-fixed"
    program = (
        "#!"
        + sys.executable
        + " -I\nimport hashlib,os,pathlib,sys\n"
        + "pins="
        + repr(pins)
        + "\n"
        + "if any(hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()!=h "
        "for p,h in pins.items()):raise SystemExit('FIXED_DAEMON_PIN_CHANGED')\n"
        + "assert pathlib.Path("
        + repr(str(plugins / "docker-compose"))
        + ").resolve()==pathlib.Path("
        + repr(str(plugin.resolve()))
        + "),'FIXED_COMPOSE_PLUGIN_CHANGED'\n"
        + "flags=('--host','--context','--config','-H','--tls',"
        "'--tlscacert','--tlscert','--tlskey')\n"
        + "if any(a==f or a.startswith(f+'=') or (f=='-H' and a.startswith('-H')) "
        "for a in sys.argv[1:] for f in flags):"
        "raise SystemExit('DAEMON_SELECTION_OVERRIDE_REFUSED')\n"
        + "os.execve("
        + repr(str(tool))
        + ",["
        + repr(str(tool))
        + ",'--host',"
        + repr(endpoint)
        + ",*sys.argv[1:]],"
        + repr(environment)
        + ")\n"
    )
    private(shim, program)
    shim.chmod(0o700)
    private(
        directory / "daemon-binding.json",
        json.dumps(
            {
                "shim": str(shim),
                "shim_sha256": file_hash(shim),
                "pins": pins,
                "endpoint": endpoint,
                "server_id": receipt["docker_server_id"],
                "scope": "NEW_HOME_CONFIG_NO_OLD_CREDENTIALS",
            }
        ),
    )
    return shim


def load(directory: Path) -> Path:
    path = directory / "daemon-binding.json"
    if path.is_symlink():
        raise ValueError("FIXED_DAEMON_BINDING_SYMLINK")
    value = json.loads(path.read_text())
    shim = directory / "docker-fixed"
    if value["shim"] != str(shim) or shim.is_symlink() or file_hash(shim) != value["shim_sha256"]:
        raise ValueError("FIXED_DAEMON_SHIM_CHANGED")
    plugin = directory / "docker-config/cli-plugins/docker-compose"
    if not plugin.is_symlink() or str(plugin.resolve()) not in value["pins"]:
        raise ValueError("FIXED_COMPOSE_PLUGIN_CHANGED")
    if any(file_hash(Path(p)) != h for p, h in value["pins"].items()):
        raise ValueError("FIXED_DAEMON_PIN_CHANGED")
    return shim
