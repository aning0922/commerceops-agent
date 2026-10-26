"""Bounded local synthetic shop lifecycle; secrets never enter arguments or stdout."""

from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import ipaddress
import json
import os
import re
import secrets
import signal
import socket
import ssl
import stat
import subprocess
import sys
import time
import urllib.parse
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from commerceops.adapters.commerce.woocommerce_deadline import WooDeadlineTransport

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "compose.woo-lab.yml"
FIXTURE = ROOT / "tests/fixtures/woocommerce-local/seed.json"
PROJECT = re.compile(r"woolab-[a-f0-9]{12}\Z")
PRIVATE_POOLS = tuple(
    ipaddress.IPv4Network(v) for v in ("10.247.0.0/16", "172.16.0.0/12", "192.168.0.0/16")
)


_operation_deadline: ContextVar[float | None] = ContextVar("woo_lab_deadline", default=None)


def bounded_timeout(limit: float) -> float:
    deadline = _operation_deadline.get()
    left = limit if deadline is None else min(limit, deadline - time.monotonic())
    if left <= 0:
        raise LabFailure("LAB_DEADLINE")
    return left


class LabFailure(RuntimeError):
    """Fixed safe diagnostic only; never include request/response or subprocess text."""


def write_private(path: Path, value: Any) -> None:
    raw = value if isinstance(value, bytes) else (json.dumps(value, indent=2) + "\n").encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
    path.chmod(0o600)


def load(directory: Path) -> dict[str, Any]:
    directory = directory.absolute()
    if directory.is_symlink() or directory.resolve() != directory:
        raise LabFailure("LAB_PRIVATE_PATH")
    if directory.parent != ROOT / "runtime" or not PROJECT.fullmatch(directory.name):
        raise LabFailure("LAB_PRIVATE_SCOPE")
    info = directory.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise LabFailure("LAB_PRIVATE_MODE")
    for file in directory.iterdir():
        if file.is_symlink() or (file.is_file() and stat.S_IMODE(file.stat().st_mode) != 0o600):
            raise LabFailure("LAB_PRIVATE_FILE_MODE")
    config: dict[str, Any] = json.loads((directory / "lab.json").read_text())
    if (
        type(config["port"]) is not int
        or not 1024 <= config["port"] <= 65535
        or config["url"] != f"https://localhost:{config['port']}"
    ):
        raise LabFailure("LAB_ORIGIN_BINDING")
    if config["project"] != directory.name or config["checkout"] != str(ROOT):
        raise LabFailure("LAB_CHECKOUT_BINDING")
    return config


def command(
    args: list[str], directory: Path, name: str, timeout: float, *, sensitive_output: bool = False
) -> bytes:
    timeout = bounded_timeout(timeout)
    started = time.monotonic()
    name = name + "-" + uuid4().hex[:8]
    try:
        result = subprocess.run(
            args,
            cwd=ROOT,
            capture_output=True,
            timeout=timeout,
            check=False,
            env={k: v for k, v in os.environ.items() if not k.startswith(("WOO_LAB_", "COMPOSE_"))},
        )
    except subprocess.TimeoutExpired as error:
        # Never retain exception text/chaining: TimeoutExpired may contain secret output.
        write_private(
            directory / f"{name}.safe.json",
            {
                "exit": "timeout",
                "seconds": timeout,
                "stdout_bytes": len(error.stdout or b""),
                "stderr_bytes": len(error.stderr or b""),
                "stdout_sha256": hashlib.sha256(error.stdout or b"").hexdigest(),
                "stderr_sha256": hashlib.sha256(error.stderr or b"").hexdigest(),
            },
        )
        raise LabFailure("LAB_COMMAND_TIMEOUT") from None
    log_content = result.stdout + result.stderr
    if sensitive_output:
        tags = [b"LAB_SENSITIVE_COMMAND_OUTPUT_SUPPRESSED"]
        log_content = (
            b"Sensitive command output suppressed. Safe diagnostics: " + b",".join(tags) + b"\n"
        )
    write_private(directory / f"{name}.private.log", log_content)
    write_private(
        directory / f"{name}.safe.json",
        {
            "exit": result.returncode,
            "seconds": round(time.monotonic() - started, 3),
            "stdout_sha256": hashlib.sha256(result.stdout).hexdigest(),
            "stderr_sha256": hashlib.sha256(result.stderr).hexdigest(),
            "stdout_bytes": len(result.stdout),
            "stderr_bytes": len(result.stderr),
        },
    )
    if result.returncode:
        raise LabFailure("LAB_COMMAND_FAILED_" + name.upper().replace("-", "_"))
    bounded_timeout(1)  # A native late exit must not advance the owner workflow.
    return result.stdout


def compose(config: dict[str, Any], directory: Path, *args: str, timeout: float = 120) -> bytes:
    envfile = directory / "compose.env"
    return command(
        [
            "docker",
            "compose",
            "--env-file",
            str(envfile),
            "-p",
            config["project"],
            "-f",
            str(COMPOSE),
            *args,
        ],
        directory,
        "compose-" + args[0],
        timeout,
        sensitive_output=any(
            arg.endswith(("/bootstrap.php", "/seed.php", "/rotate-key.php")) for arg in args
        ),
    )


def classify_route(
    network: ipaddress.IPv4Network,
    gateway: str,
    interface: str,
    flags: str,
    capture_group: tuple[str, str] | None,
) -> str:
    private = [ipaddress.IPv4Network(v) for v in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")]
    captures_private_block = any(block != network and block.subnet_of(network) for block in private)
    if (
        capture_group is not None
        and (gateway, interface) == capture_group
        and "G" in flags
        and captures_private_block
    ):
        return "broad_capture_overlap"
    return "hard_exclusion"


def host_route_inventory() -> tuple[list[ipaddress.IPv4Network], dict[str, Any]]:
    capture_group = None
    probes = []
    if sys.platform == "darwin":
        raw = subprocess.check_output(
            ["netstat", "-rn", "-f", "inet"], cwd=ROOT, timeout=bounded_timeout(10)
        ).decode()
        parsed = [line.split() for line in raw.splitlines() if line.split()]
        for target in ("1.1.1.1", "8.8.8.8", "203.0.113.1"):
            text = subprocess.check_output(
                ["route", "-n", "get", target], cwd=ROOT, timeout=bounded_timeout(10)
            ).decode()
            data = dict(re.findall(r"^\s*(gateway|interface):\s*(\S+)", text, re.MULTILINE))
            probes.append({"target": target, **data})
        pairs = {(p.get("gateway", ""), p.get("interface", "")) for p in probes}
        if len(pairs) == 1:
            gateway, interface = next(iter(pairs))
            try:
                synthetic_gateway = ipaddress.IPv4Address(gateway) in ipaddress.IPv4Network(
                    "198.18.0.0/15"
                )
            except ValueError:
                synthetic_gateway = False
            if synthetic_gateway and re.fullmatch(r"utun[0-9]+", interface):
                capture_group = gateway, interface
    elif sys.platform == "linux":
        raw = subprocess.check_output(
            ["ip", "-j", "-4", "route", "show", "table", "all"],
            cwd=ROOT,
            timeout=bounded_timeout(10),
        ).decode()
        parsed = [
            [r.get("dst", "default"), r.get("gateway", ""), "", r.get("dev", "")]
            for r in json.loads(raw)
        ]
    else:
        raise LabFailure("LAB_HOST_ROUTE_PLATFORM")
    hard, records = [], []
    for fields in parsed:
        value = fields[0]
        if value == "default" or not re.fullmatch(r"[0-9./]+", value):
            continue
        address, separator, prefix = value.partition("/")
        count = address.count(".") + 1
        address += ".0" * (4 - count)
        try:
            network = ipaddress.IPv4Network(
                address + "/" + (prefix if separator else str(count * 8)), strict=False
            )
        except ValueError:
            raise LabFailure("LAB_HOST_ROUTE_INVALID") from None
        if network.prefixlen == 0:
            continue
        if len(fields) < 4:
            raise LabFailure("LAB_HOST_ROUTE_FIELDS")
        classification = classify_route(network, fields[1], fields[3], fields[2], capture_group)
        records.append(
            {
                "original_destination": value,
                "network": str(network),
                "gateway": fields[1],
                "interface": fields[3],
                "flags": fields[2],
                "classification": classification,
            }
        )
        if classification == "hard_exclusion":
            hard.append(network)
    return hard, {
        "raw_route_table": raw,
        "capture_probes": probes,
        "routes": records,
        "scope": "Docker Desktop VM plus localhost publishing; broad coverage remains",
    }


def host_networks() -> list[ipaddress.IPv4Network]:
    return host_route_inventory()[0]


def occupied_networks() -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    ids = (
        subprocess.check_output(
            ["docker", "network", "ls", "-q"], cwd=ROOT, timeout=bounded_timeout(20)
        )
        .decode()
        .split()
    )
    rows = (
        json.loads(
            subprocess.check_output(
                ["docker", "network", "inspect", *ids], cwd=ROOT, timeout=bounded_timeout(30)
            )
        )
        if ids
        else []
    )
    networks = [
        ipaddress.ip_network(c["Subnet"])
        for row in rows
        for c in (row.get("IPAM", {}).get("Config") or [])
        if c.get("Subnet")
    ]
    networks.extend(host_networks())
    return networks


def available_subnets() -> list[str]:
    occupied = occupied_networks()
    selected: list[str] = []
    for pool in PRIVATE_POOLS:
        for candidate in pool.subnets(new_prefix=28):
            if any(
                candidate.version == net.version and candidate.overlaps(net) for net in occupied
            ):
                continue
            selected.append(str(candidate))
            if len(selected) == 2:
                return selected
    raise LabFailure("LAB_NO_UNUSED_SUBNET")


def check_network_allocation(config: dict[str, Any], directory: Path) -> None:
    selected = [ipaddress.IPv4Network(config[key]) for key in ("internal_subnet", "ingress_subnet")]
    if selected[0] == selected[1] or any(
        net.prefixlen != 28 or not any(net.subnet_of(pool) for pool in PRIVATE_POOLS)
        for net in selected
    ):
        raise LabFailure("LAB_SUBNET_SCOPE")
    occupied = occupied_networks()
    if any(
        net.version == other.version and net.overlaps(other)
        for net in selected
        for other in occupied
    ):
        raise LabFailure("LAB_SUBNET_OVERLAP")
    write_private(
        directory / "allocation.safe.json",
        {
            "selected": [str(n) for n in selected],
            "specific_docker_host_subnet_conflict": False,
            "host_route_evidence": host_route_inventory()[1],
            "utc": datetime.now(UTC).isoformat(),
        },
    )


def prepare() -> Path:
    os.umask(0o077)
    subnets = available_subnets()
    project = "woolab-" + uuid4().hex[:12]
    directory = ROOT / "runtime" / project
    directory.mkdir(mode=0o700, parents=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"https://localhost:{port}"
    config = {
        "schema": "woo-local-lab-v1",
        "project": project,
        "port": port,
        "url": url,
        "checkout": str(ROOT),
        "created_at": datetime.now(UTC).isoformat(),
        "internal_subnet": subnets[0],
        "ingress_subnet": subnets[1],
    }
    write_private(directory / "lab.json", config)
    write_private(
        directory / "initial.json",
        {
            "url": url,
            "admin_user": "lab_owner_" + secrets.token_hex(4),
            "admin_password": secrets.token_urlsafe(32),
            "reader_user": "lab_reader_" + secrets.token_hex(4),
            "reader_password": secrets.token_urlsafe(32),
        },
    )
    for name in ("db_password", "db_root_password"):
        write_private(directory / name, (secrets.token_urlsafe(32) + "\n").encode())
    write_private(
        directory / "compose.env",
        (
            f"WOO_LAB_PROJECT={project}\nWOO_LAB_PRIVATE_DIR={directory}\nWOO_LAB_PORT={port}\n"
            f"WOO_LAB_INTERNAL_SUBNET={subnets[0]}\nWOO_LAB_INGRESS_SUBNET={subnets[1]}\n"
        ).encode(),
    )
    extension = (
        b"subjectAltName=DNS:localhost,IP:127.0.0.1\n"
        b"basicConstraints=critical,CA:FALSE\n"
        b"keyUsage=critical,digitalSignature,keyEncipherment\n"
        b"extendedKeyUsage=serverAuth\n"
    )
    write_private(directory / "server.ext", extension)
    command(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "30",
            "-subj",
            "/CN=CommerceOps dedicated synthetic lab CA",
            "-keyout",
            str(directory / "ca.key"),
            "-out",
            str(directory / "ca.crt"),
            "-addext",
            "basicConstraints=critical,CA:TRUE",
            "-addext",
            "keyUsage=critical,keyCertSign,cRLSign",
        ],
        directory,
        "ca",
        30,
    )
    command(
        [
            "openssl",
            "req",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-subj",
            "/CN=localhost",
            "-keyout",
            str(directory / "server.key"),
            "-out",
            str(directory / "server.csr"),
        ],
        directory,
        "csr",
        30,
    )
    command(
        [
            "openssl",
            "x509",
            "-req",
            "-in",
            str(directory / "server.csr"),
            "-CA",
            str(directory / "ca.crt"),
            "-CAkey",
            str(directory / "ca.key"),
            "-set_serial",
            str(int.from_bytes(os.urandom(16), "big")),
            "-days",
            "30",
            "-out",
            str(directory / "server.crt"),
            "-extfile",
            str(directory / "server.ext"),
        ],
        directory,
        "certificate",
        30,
    )
    for file in directory.iterdir():
        file.chmod(0o600)
    return directory


@contextmanager
def exclusive(directory: Path) -> Iterator[None]:
    fd = os.open(directory / "owner.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise LabFailure("LAB_ALREADY_RUNNING") from error
        yield
    finally:
        os.close(fd)


def owned_inventory(config: dict[str, Any], directory: Path) -> list[dict[str, Any]]:
    ids = (
        command(
            [
                "docker",
                "ps",
                "-aq",
                "--filter",
                f"label=com.docker.compose.project={config['project']}",
            ],
            directory,
            "inventory",
            20,
        )
        .decode()
        .split()
    )
    if not ids:
        return []
    rows: list[dict[str, Any]] = json.loads(
        command(["docker", "inspect", *ids], directory, "inspect", 30)
    )
    for row in rows:
        labels = row["Config"]["Labels"]
        if labels.get("com.docker.compose.project") != config["project"] or labels.get(
            "com.docker.compose.project.working_dir"
        ) != str(ROOT):
            raise LabFailure("LAB_RESOURCE_OWNERSHIP")
    return rows


def stop(config: dict[str, Any], directory: Path) -> None:
    owned_inventory(config, directory)
    compose(config, directory, "down", "--timeout", "20", timeout=90)
    if owned_inventory(config, directory):
        raise LabFailure("LAB_CLEANUP_CONTAINERS")
    networks = command(
        [
            "docker",
            "network",
            "ls",
            "-q",
            "--filter",
            f"label=com.docker.compose.project={config['project']}",
        ],
        directory,
        "networks",
        20,
    )
    if networks.strip():
        raise LabFailure("LAB_CLEANUP_NETWORK")
    volumes = (
        command(
            [
                "docker",
                "volume",
                "ls",
                "-q",
                "--filter",
                f"label=com.docker.compose.project={config['project']}",
            ],
            directory,
            "volumes",
            20,
        )
        .decode()
        .split()
    )
    with socket.socket() as sock:
        sock.settimeout(bounded_timeout(2))
        listener_absent = sock.connect_ex(("127.0.0.1", config["port"])) != 0
    if not listener_absent:
        raise LabFailure("LAB_CLEANUP_LISTENER")
    bounded_timeout(1)
    write_private(
        directory / "cleanup.safe.json",
        {
            "containers": 0,
            "networks": 0,
            "listener_absent": True,
            "volumes_retained": volumes,
            "utc": datetime.now(UTC).isoformat(),
        },
    )


class Client:
    def __init__(self, config: dict[str, Any], directory: Path, deadline: float):
        self.url = config["url"]
        self.deadline = deadline
        self.requests = 0
        self.context = ssl.create_default_context(cafile=str(directory / "ca.crt"))
        auth = json.loads((directory / "runtime-auth.json").read_text())
        self.authorization = (
            "Basic "
            + base64.b64encode(
                (auth["consumer_key"] + ":" + auth["consumer_secret"]).encode()
            ).decode()
        )

    def remaining(self) -> float:
        left = self.deadline - time.monotonic()
        if left <= 0:
            raise LabFailure("LAB_DEADLINE")
        return bounded_timeout(left)

    def read_response(
        self,
        path: str,
        method: str = "GET",
        payload: Any = None,
        *,
        context: ssl.SSLContext | None = None,
        authenticated: bool = False,
        max_bytes: int = 2097152,
    ) -> tuple[int, bytes, httpx.Headers]:
        if not path.startswith("/") or path.startswith("//") or ".." in path or "#" in path:
            raise LabFailure("LAB_REQUEST_SCOPE")
        self.requests += 1
        if self.requests > 128:
            raise LabFailure("LAB_READ_BUDGET")
        self.remaining()
        headers = {"Accept-Encoding": "identity", "Content-Type": "application/json"}
        if authenticated:
            headers["Authorization"] = self.authorization
        body = None if payload is None else json.dumps(payload).encode()
        try:
            # Reuse the reviewed A transport: every recv/write/TLS/connect takes the
            # current remaining time. This also bounds headers and error bodies.
            with (
                httpx.Client(
                    transport=WooDeadlineTransport(context or self.context, self.remaining),
                    trust_env=False,
                    follow_redirects=False,
                ) as client,
                client.stream(
                    method,
                    self.url + path,
                    content=body,
                    headers=headers,
                    timeout=min(15, self.remaining()),
                ) as response,
            ):
                data = bytearray()
                for chunk in response.iter_raw():
                    self.remaining()
                    if len(data) + len(chunk) > max_bytes:
                        raise LabFailure("LAB_RESPONSE_LIMIT")
                    data.extend(chunk)
                self.remaining()
                return response.status_code, bytes(data), response.headers
        except httpx.TimeoutException:
            raise LabFailure("LAB_DEADLINE") from None
        except httpx.TransportError as error:
            cause: BaseException | None = error
            tls = False
            untrusted = False
            for _ in range(10):
                if cause is None:
                    break
                tls |= isinstance(cause, ssl.SSLError)
                untrusted |= isinstance(cause, ssl.SSLCertVerificationError)
                cause = cause.__cause__ or cause.__context__
            raise LabFailure(
                "LAB_TLS_UNTRUSTED"
                if untrusted
                else "LAB_TLS_FAILED"
                if tls
                else "LAB_CONNECTION_FAILED"
            ) from None

    def request(self, path: str, method: str = "GET", payload: Any = None) -> tuple[int, Any, Any]:
        if not path.startswith("/wp-json/wc/v3/"):
            raise LabFailure("LAB_REQUEST_SCOPE")
        code, raw, headers = self.read_response(path, method, payload, authenticated=True)
        result = json.loads(raw)
        self.remaining()  # Parsing/late injected responses cannot publish success either.
        return code, result, headers

    def pages(self, path: str, per_page: int = 2) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        pages = 1
        for page in range(1, 101):
            code, rows, headers = self.request(
                path
                + ("&" if "?" in path else "?")
                + urllib.parse.urlencode(
                    {"per_page": per_page, "page": page, "orderby": "id", "order": "asc"}
                )
            )
            if code != 200 or not isinstance(rows, list):
                raise LabFailure("LAB_READ_FAILED")
            total, pages = int(headers["X-WP-Total"]), int(headers["X-WP-TotalPages"])
            items.extend(rows)
            if page >= pages:
                if len(items) != total or len({x["id"] for x in items}) != len(items):
                    raise LabFailure("LAB_PAGINATION_INCOMPLETE")
                return items
        raise LabFailure("LAB_PAGE_LIMIT")


def runtime_boundary(config: dict[str, Any], directory: Path) -> None:
    rows = owned_inventory(config, directory)
    by_service = {row["Config"]["Labels"]["com.docker.compose.service"]: row for row in rows}
    if set(by_service) != {"database", "wordpress", "tls"}:
        raise LabFailure("LAB_RESOURCE_SET")
    internal = config["project"] + "_isolated"
    ingress = config["project"] + "_ingress"
    for service in ("database", "wordpress"):
        if set(by_service[service]["NetworkSettings"]["Networks"]) != {internal}:
            raise LabFailure("LAB_BACKEND_NETWORK")
    tls = by_service["tls"]
    if set(tls["NetworkSettings"]["Networks"]) != {internal, ingress}:
        raise LabFailure("LAB_TLS_NETWORK")
    if tls["NetworkSettings"]["Ports"].get("8443/tcp") != [
        {"HostIp": "127.0.0.1", "HostPort": str(config["port"])}
    ]:
        raise LabFailure("LAB_LISTENER_NOT_LOOPBACK")
    if any(
        row["HostConfig"]["Privileged"] or row["HostConfig"]["NetworkMode"] == "host"
        for row in rows
    ):
        raise LabFailure("LAB_PRIVILEGED_RESOURCE")
    status = compose(
        config, directory, "exec", "-T", "--user", "101", "tls", "cat", "/proc/1/status", timeout=10
    ).decode()
    fields = dict(line.split(":", 1) for line in status.splitlines() if ":" in line)
    caps = {
        name: fields[name].strip() for name in ("CapEff", "CapPrm", "CapInh", "CapAmb", "CapBnd")
    }
    if any(int(caps[name], 16) for name in ("CapEff", "CapPrm", "CapInh", "CapAmb")):
        raise LabFailure("LAB_TLS_CAPS_NOT_DROPPED")
    if set(fields["Uid"].split()) != {"101"} or fields["NoNewPrivs"].strip() != "1":
        raise LabFailure("LAB_TLS_PRIVILEGE_STATE")
    routes = (
        compose(config, directory, "exec", "-T", "--user", "101", "tls", "ip", "route", timeout=10)
        .decode()
        .splitlines()
    )
    if any(line.startswith("default ") for line in routes):
        raise LabFailure("LAB_TLS_DEFAULT_ROUTE")
    networks = json.loads(
        command(["docker", "network", "inspect", internal, ingress], directory, "network-proof", 10)
    )
    if not next(n for n in networks if n["Name"] == internal)["Internal"]:
        raise LabFailure("LAB_INTERNAL_NETWORK_DISABLED")
    ipv6_routes = (
        compose(
            config, directory, "exec", "-T", "--user", "101", "tls", "ip", "-6", "route", timeout=10
        )
        .decode()
        .splitlines()
    )
    if any(line.startswith("default ") for line in ipv6_routes):
        raise LabFailure("LAB_TLS_IPV6_DEFAULT_ROUTE")
    vm_raw = compose(
        config,
        directory,
        "exec",
        "-T",
        "--user",
        "101",
        "tls",
        "sh",
        "-c",
        "getent hosts host.docker.internal; getent hosts gateway.docker.internal",
        timeout=10,
    ).decode()
    vm4_raw = compose(
        config,
        directory,
        "exec",
        "-T",
        "wordpress",
        "php",
        "-r",
        'echo json_encode([gethostbynamel("host.docker.internal"),'
        'gethostbynamel("gateway.docker.internal")]);',
        timeout=10,
    )
    vm4 = json.loads(vm4_raw)
    if any(row is not False and not isinstance(row, list) for row in vm4):
        raise LabFailure("LAB_DESKTOP_DNS_RESULT_INVALID")
    vm_addresses = sorted(
        {line.split()[0] for line in vm_raw.splitlines() if line.split()}
        | {address for row in vm4 if isinstance(row, list) for address in row}
    )
    if not vm_addresses:
        raise LabFailure("LAB_DESKTOP_TRANSPORT_UNKNOWN")
    selected_nets = [
        ipaddress.IPv4Network(config[k]) for k in ("internal_subnet", "ingress_subnet")
    ]
    if any(
        ipaddress.ip_address(address) in net for address in vm_addresses for net in selected_nets
    ):
        raise LabFailure("LAB_DESKTOP_TRANSPORT_CONFLICT")
    if any(n["EnableIPv6"] for n in networks):
        raise LabFailure("LAB_UNEXPECTED_IPV6_NETWORK")
    installed_raw = compose(
        config,
        directory,
        "exec",
        "-T",
        "wordpress",
        "php",
        "-r",
        'echo json_encode(["bootstrap.php"=>hash_file("sha256","/opt/woo-lab/bootstrap.php"),'
        '"seed.php"=>hash_file("sha256","/opt/woo-lab/seed.php"),'
        '"safety.php"=>hash_file("sha256","/opt/woo-lab/safety.php"),'
        '"lockdown.php"=>hash_file("sha256","/var/www/html/wp-content/mu-plugins/commerceops-lab.php")]);',
        timeout=10,
    )
    installed = json.loads(installed_raw)
    expected_files = {
        name: hashlib.sha256((ROOT / "infrastructure/woo-lab" / name).read_bytes()).hexdigest()
        for name in ("bootstrap.php", "seed.php", "safety.php", "lockdown.php")
    }
    if installed != expected_files:
        raise LabFailure("LAB_INSTALLED_SOURCE_MISMATCH")
    write_private(
        directory / "runtime-boundary.safe.json",
        {
            "installed_source_hashes": installed,
            "ipv6_routes": ipv6_routes,
            "observed_desktop_transport_addresses": vm_addresses,
            "desktop_transport_cidr": "not_reported_by_settings_store",
            "desktop_ipv4_dns_available": all(isinstance(row, list) and row for row in vm4),
            "specific_transport_address_conflict": False,
            "dns_host_gateway_scope": (
                "embedded DNS exists; no claim of zero arbitrary protocol egress"
            ),
            "tls_uid": 101,
            "capabilities": caps,
            "no_new_privileges": True,
            "default_route_absent": True,
            "routes": routes,
            "backend_internal_only": True,
            "published_loopback_only": True,
            "privileged": False,
            "host_network": False,
            "images": {name: row["Image"] for name, row in by_service.items()},
            "memory_limits": {
                name: row["HostConfig"]["Memory"] for name, row in by_service.items()
            },
            "utc": datetime.now(UTC).isoformat(),
        },
    )


def initialize(config: dict[str, Any], directory: Path, deadline: float) -> dict[str, Any]:
    compose(
        config,
        directory,
        "exec",
        "-T",
        "wordpress",
        "wp",
        "eval-file",
        "/opt/woo-lab/bootstrap.php",
        "--skip-wordpress",
        "--allow-root",
        timeout=min(120, deadline - time.monotonic() - 90),
    )
    raw = compose(
        config,
        directory,
        "exec",
        "-T",
        "wordpress",
        "wp",
        "eval-file",
        "/opt/woo-lab/seed.php",
        "--allow-root",
        timeout=min(120, deadline - time.monotonic() - 90),
    )
    try:
        result: dict[str, Any] = json.loads(raw)
    except ValueError as error:
        raise LabFailure("LAB_SEED_RESULT_INVALID") from error
    write_private(directory / "runtime-auth.json", result.pop("runtime_auth"))
    write_private(directory / "seed-result.private.json", result)
    safety = compose(
        config,
        directory,
        "exec",
        "-T",
        "wordpress",
        "wp",
        "eval-file",
        "/opt/woo-lab/safety.php",
        "--allow-root",
        timeout=min(30, deadline - time.monotonic() - 90),
    )
    write_private(directory / "runtime-safety.safe.json", json.loads(safety))
    from scripts.woo_lab.expectations import write_handoff

    write_handoff(config, directory, result)
    return result


def verify(
    config: dict[str, Any], directory: Path, first: dict[str, Any], deadline: float
) -> dict[str, Any]:
    from scripts.woo_lab.verify import verify_shop

    return verify_shop(Client(config, directory, deadline - 90), config, directory, first)


def run(config: dict[str, Any], directory: Path, seconds: int, serving: bool) -> None:
    if not 300 <= seconds <= 3600:
        raise LabFailure("LAB_DURATION_RANGE")
    deadline = time.monotonic() + seconds
    primary: str | None = None
    started_here = False
    token = _operation_deadline.set(deadline - 90)
    try:
        if owned_inventory(config, directory):
            raise LabFailure("LAB_RESOURCES_ALREADY_EXIST")
        check_network_allocation(config, directory)
        started_here = True
        compose(config, directory, "up", "-d", "--wait", "--wait-timeout", "120", timeout=150)
        runtime_boundary(config, directory)
        first = initialize(config, directory, deadline)
        bounded_timeout(1)
        if serving:
            print(
                json.dumps(
                    {
                        "url": config["url"],
                        "credentials_file": str(directory / "initial.json"),
                        "readonly_key_file": str(directory / "runtime-auth.json"),
                        "ca_file": str(directory / "ca.crt"),
                        "lifetime_seconds": seconds,
                    }
                ),
                flush=True,
            )
            while time.monotonic() < deadline - 90:
                time.sleep(min(1, max(0, deadline - 90 - time.monotonic())))
        else:
            verified = verify(config, directory, first, deadline)
            bounded_timeout(1)
            write_private(directory / "verification.safe.json", verified)
            if time.monotonic() >= deadline - 90:
                raise LabFailure("LAB_CLEANUP_RESERVE")
            again = initialize(config, directory, deadline)
            if first != again:
                raise LabFailure("LAB_RESEED_MAPPING_CHANGED")
            verified_again = verify(config, directory, again, deadline)
            bounded_timeout(1)
            write_private(
                directory / "reseed.safe.json",
                {
                    "same_mapping": True,
                    "no_extra_objects": True,
                    "verification": verified_again,
                },
            )
    except BaseException as error:
        primary = str(error) if isinstance(error, LabFailure) else type(error).__name__
        write_private(
            directory / f"failure-{uuid4().hex[:8]}.safe.json",
            {"category": primary, "utc": datetime.now(UTC).isoformat()},
        )
        raise
    finally:
        _operation_deadline.set(deadline)  # The original total includes cleanup.
        try:
            if started_here:
                try:
                    if primary is not None:
                        compose(config, directory, "logs", "--no-color", "--tail", "80", timeout=20)
                finally:
                    stop(config, directory)
        except BaseException:
            write_private(
                directory / f"cleanup-failure-{uuid4().hex[:8]}.safe.json",
                {"primary": primary, "category": "LAB_CLEANUP_FAILED"},
            )
            raise
        finally:
            _operation_deadline.reset(token)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "build", "verify", "serve", "stop"])
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--seconds", type=int, default=600)
    args = parser.parse_args()
    os.umask(0o077)
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        if args.action == "prepare":
            print(prepare())
            return
        if args.directory is None:
            raise LabFailure("LAB_DIRECTORY_REQUIRED")
        directory = args.directory.absolute()
        config = load(directory)
        with exclusive(directory):
            if args.action == "build":
                compose(config, directory, "build", "--pull", "wordpress", timeout=600)
                compose(config, directory, "pull", "database", "tls", timeout=450)
            elif args.action == "stop":
                stop(config, directory)
            else:
                run(config, directory, args.seconds, args.action == "serve")
        print(
            json.dumps({"status": "complete", "action": args.action, "directory": str(directory)})
        )
    except (LabFailure, OSError, ValueError, KeyError, TypeError, KeyboardInterrupt) as error:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "category": str(error)
                    if isinstance(error, LabFailure)
                    else type(error).__name__,
                }
            )
        )
        raise SystemExit(1) from None
