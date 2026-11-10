"""Explicit subnet contract; Docker inventory is synthetic, no daemon access."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from . import owned_driver as driver
from .supervisor import Budget
from .test_owned_driver import case as case

pytestmark = pytest.mark.offline


@pytest.mark.parametrize(
    "pg,host",
    [
        ("10.242.10.0/24", "10.242.11.0/24"),
        ("172.16.0.0/24", "172.31.255.0/24"),
        ("192.168.0.0/24", "192.168.1.0/24"),
    ],
)
def test_explicit_canonical_private_pairs_accepted(pg: str, host: str) -> None:
    driver.validate_subnets(pg, host)


@pytest.mark.parametrize(
    "value",
    [
        "10.242.10.1/24",
        "10.242.10.0/23",
        "10.242.10.0/255.255.255.0",
        "10.242.10/24",
        "8.8.8.0/24",
        "100.64.0.0/24",
        "127.0.0.0/24",
        "169.254.0.0/24",
        "fc00::/24",
        "172.32.0.0/24",
        " 10.242.10.0/24",
        "",
    ],
)
def test_no_normalization_public_or_default_subnet_fallback(value: str) -> None:
    with pytest.raises(ValueError):
        driver.validate_subnets(value, "10.242.11.0/24")


def test_two_requested_ranges_must_not_overlap() -> None:
    with pytest.raises(ValueError):
        driver.validate_subnets("10.242.10.0/24", "10.242.10.0/24")


def inspect_fixture(
    case: driver.Case,
    monkeypatch: pytest.MonkeyPatch,
    row: dict[str, Any],
    *,
    changed: bool = False,
    malformed: bool = False,
) -> dict[str, Any]:
    calls: list[list[str]] = []

    def capture(command: list[str], *args: object, **kwargs: object) -> bytes:
        calls.append(command)
        assert command[1:3] in (["network", "ls"], ["network", "inspect"])
        if command[2] == "ls":
            return (("b" if changed and len(calls) > 1 else "a") * 64 + "\n").encode()
        return b"not-json" if malformed else json.dumps(row).encode()

    monkeypatch.setattr(driver, "checked", capture)
    now = datetime.now(UTC)
    return driver.verify_existing_subnets(
        case, "/docker", Budget.bind(now, now + timedelta(minutes=5)), []
    )


def row(
    config: object, *, name: str = "observed", network_driver: str = "bridge"
) -> dict[str, Any]:
    return dict(id="a" * 64, name=name, driver=network_driver, ipam=config)


def test_disjoint_actual_inventory_accepts_and_checks_stable_ids(
    case: driver.Case,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = inspect_fixture(case, monkeypatch, row([{"Subnet": "10.0.0.0/8"}]))
    assert report["status"] == "NO_OVERLAP_OBSERVED" and report["inspected_networks"] == 1


@pytest.mark.parametrize("subnet", ["172.30.250.0/24", "172.30.251.0/24", "172.16.0.0/12"])
def test_either_requested_range_or_broader_existing_range_overlap_refused(
    case: driver.Case,
    monkeypatch: pytest.MonkeyPatch,
    subnet: str,
) -> None:
    with pytest.raises(ValueError, match="overlaps"):
        inspect_fixture(case, monkeypatch, row([{"Subnet": subnet}]))


@pytest.mark.parametrize("config", [None, [], {}, [{"Gateway": "unknown"}], [{"Subnet": "bad"}]])
def test_unknown_or_malformed_ipam_is_not_treated_as_free_space(
    case: driver.Case,
    monkeypatch: pytest.MonkeyPatch,
    config: object,
) -> None:
    with pytest.raises(ValueError):
        inspect_fixture(case, monkeypatch, row(config))


@pytest.mark.parametrize("name,network_driver", [("host", "host"), ("none", "null")])
def test_only_known_builtin_no_l3_networks_may_have_no_subnet(
    case: driver.Case,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    network_driver: str,
) -> None:
    inspect_fixture(case, monkeypatch, row(None, name=name, network_driver=network_driver))


@pytest.mark.parametrize("changed,malformed", [(True, False), (False, True)])
def test_changing_inventory_and_bad_json_failclosed(
    case: driver.Case,
    monkeypatch: pytest.MonkeyPatch,
    changed: bool,
    malformed: bool,
) -> None:
    with pytest.raises(ValueError):
        inspect_fixture(
            case, monkeypatch, row([{"Subnet": "10.0.0.0/8"}]), changed=changed, malformed=malformed
        )


def test_required_root_subnets_go_into_env_and_ipam_without_defaults(case: driver.Case) -> None:
    driver.prepare(case)
    env = (Path(case.directory) / "compose.env").read_text()
    assert f"V4_PG_SUBNET={case.pg_subnet}\n" in env
    assert f"V4_HOST_SUBNET={case.host_subnet}\n" in env
    model = json.loads(Path(driver.__file__).with_name("owned.compose.yml").read_text())
    assert model["networks"]["default"]["ipam"]["config"] == [
        {"subnet": "${V4_PG_SUBNET:?Root explicit PG subnet required}"}
    ]
    assert model["networks"]["host_facing"]["ipam"]["config"] == [
        {"subnet": "${V4_HOST_SUBNET:?Root explicit host subnet required}"}
    ]


def test_unknown_network_driver_with_apparently_valid_range_is_refused(
    case: driver.Case,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="unknown Docker"):
        inspect_fixture(
            case, monkeypatch, row([{"Subnet": "10.0.0.0/8"}], network_driver="unknown")
        )
