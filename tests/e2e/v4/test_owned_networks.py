"""Pure topology contracts: internal PG, dual-network API, loopback host publish.

These checks do not create Docker networks or prove Desktop port forwarding.
"""

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from . import owned_driver
from .owned_driver import Case
from .test_owned_driver import case as case

pytestmark = pytest.mark.offline


def overlay() -> dict[str, Any]:
    return dict(json.loads(Path(owned_driver.__file__).with_name("owned.compose.yml").read_text()))


def test_pg_and_owner_remain_only_on_internal_network_without_pg_host_port() -> None:
    model = overlay()
    assert model["networks"]["default"]["internal"] is True
    for role in ("postgres", "pg-test"):
        service = model["services"][role]
        assert service["networks"] == ["default"]
        assert not service.get("ports")
        assert "network_mode" not in service


def test_api_alone_gets_dedicated_bridge_with_loopback_publish_and_runtime_only_mount() -> None:
    model = overlay()
    assert set(model["services"]) == {"postgres", "pg-test", "v4-api"}
    api = model["services"]["v4-api"]
    assert set(api["networks"]) == {"default", "host_facing"}
    assert model["networks"]["host_facing"] == {"driver": "bridge", "internal": False}
    assert all("name" not in net and not net.get("external") for net in model["networks"].values())
    assert api["ports"] == ["127.0.0.1:${V4_API_PORT}:${V4_API_PORT}"]
    assert api["command"] == ["python", "-m", "tests.e2e.v4.owned_api"]
    assert api["volumes"] == ["${V4_API_DIR:?new runtime-only directory required}:/run/v4_api:ro"]
    assert not api.get("secrets") and "network_mode" not in api
    assert not any(key.startswith("COMMERCEOPS_DB_") for key in api["environment"])


@pytest.mark.parametrize("normalized", [False, True])
def test_frozen_model_preserves_exact_networks_without_build_or_pull_fallback(
    case: Case,
    normalized: bool,
) -> None:
    model = overlay()
    for name, service in model["services"].items():
        service["image"] = case.pg_image if name == "postgres" else case.test_image
        service["build"] = {"context": "must-be-removed"}
        if normalized:
            service["networks"] = {network: None for network in service["networks"]}
    expected_networks = copy.deepcopy(model["networks"])
    expected_membership = {
        name: copy.deepcopy(service["networks"]) for name, service in model["services"].items()
    }
    frozen = owned_driver.no_build_model(model, case)
    assert frozen["networks"] == expected_networks
    for name, service in frozen["services"].items():
        assert service["networks"] == expected_membership[name]
        assert service["pull_policy"] == "never" and "build" not in service
