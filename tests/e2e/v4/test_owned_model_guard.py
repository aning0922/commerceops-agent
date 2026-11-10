"""Pure expanded-model drift negatives; no Docker or services."""

import pytest

from . import owned_driver as driver
from .test_owned_driver import case as case
from .test_owned_driver import expanded_model

pytestmark = pytest.mark.offline


@pytest.mark.parametrize("explicit_defaults", [False, True])
def test_observed_compose_shape_and_normalized_defaults_are_preserved(
    case: driver.Case,
    explicit_defaults: bool,
) -> None:
    model = expanded_model(case)
    if explicit_defaults:
        for key, net in model["networks"].items():
            net.update(
                internal=key == "default",
                driver="bridge",
                attachable=False,
                external=False,
                enable_ipv4=True,
                enable_ipv6=False,
            )
            net["ipam"].update(driver="default", options={})
    fixed = driver.no_build_model(model, case)
    assert fixed["networks"] == model["networks"]
    assert fixed["services"]["v4-api"]["ports"] == model["services"]["v4-api"]["ports"]


@pytest.mark.parametrize(
    "fault",
    [
        "pg_env_differs",
        "host_env_differs",
        "extra_network",
        "external_network",
        "wrong_name",
        "wrong_pg_internal",
        "wrong_host_internal",
        "wrong_driver",
        "extra_ipam_range",
        "gateway",
        "ipam_plugin",
        "pg_on_host_facing",
        "owner_on_host_facing",
        "api_missing_internal",
        "api_extra_network",
        "api_alias_override",
        "pg_host_port",
        "owner_host_port",
        "api_wildcard",
        "api_published_mismatch",
        "api_target_mismatch",
        "api_extra_port",
        "api_udp",
    ],
)
def test_expanded_drift_refused_before_model_can_be_frozen(case: driver.Case, fault: str) -> None:
    model = expanded_model(case)
    nets, services = model["networks"], model["services"]
    api_port = services["v4-api"]["ports"][0]
    if fault == "pg_env_differs":
        nets["default"]["ipam"]["config"][0]["subnet"] = "10.242.99.0/24"
    elif fault == "host_env_differs":
        nets["host_facing"]["ipam"]["config"][0]["subnet"] = "10.242.98.0/24"
    elif fault == "extra_network":
        nets["foreign"] = {}
    elif fault == "external_network":
        nets["default"]["external"] = True
    elif fault == "wrong_name":
        nets["default"]["name"] = "old_asset"
    elif fault == "wrong_pg_internal":
        nets["default"]["internal"] = False
    elif fault == "wrong_host_internal":
        nets["host_facing"]["internal"] = True
    elif fault == "wrong_driver":
        nets["host_facing"]["driver"] = "host"
    elif fault == "extra_ipam_range":
        nets["default"]["ipam"]["config"].append({"subnet": "10.99.0.0/24"})
    elif fault == "gateway":
        nets["default"]["ipam"]["config"][0]["gateway"] = "10.99.0.1"
    elif fault == "ipam_plugin":
        nets["default"]["ipam"]["driver"] = "unknown"
    elif fault in {"pg_on_host_facing", "owner_on_host_facing"}:
        services["postgres" if fault == "pg_on_host_facing" else "pg-test"]["networks"][
            "host_facing"
        ] = None
    elif fault == "api_missing_internal":
        services["v4-api"]["networks"].pop("default")
    elif fault == "api_extra_network":
        services["v4-api"]["networks"]["foreign"] = None
    elif fault == "api_alias_override":
        services["v4-api"]["networks"]["default"] = {"aliases": ["old_database"]}
    elif fault in {"pg_host_port", "owner_host_port"}:
        services["postgres" if fault == "pg_host_port" else "pg-test"]["ports"] = [api_port]
    elif fault == "api_wildcard":
        api_port["host_ip"] = "0.0.0.0"  # noqa: S104 -- negative JSON model only.
    elif fault == "api_published_mismatch":
        api_port["published"] = str(case.api_port + 1)
    elif fault == "api_target_mismatch":
        api_port["target"] = case.api_port + 1
    elif fault == "api_extra_port":
        services["v4-api"]["ports"].append(dict(api_port))
    elif fault == "api_udp":
        api_port["protocol"] = "udp"
    with pytest.raises(ValueError):
        driver.no_build_model(model, case)
