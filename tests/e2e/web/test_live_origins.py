"""纯离线反例，不连接PG或浏览器。"""

import json
from pathlib import Path

import pytest

from tests.e2e.web.live_origins import owned_origin, registered_origins

pytestmark = pytest.mark.offline


def test_registered_nondefault_3470_3471(tmp_path: Path) -> None:
    path = tmp_path / "window.json"
    path.write_text(
        json.dumps({"web_origin": "http://127.0.0.1:3470", "api_origin": "http://127.0.0.1:3471"})
    )
    path.chmod(0o600)
    assert registered_origins(tmp_path) == ("http://127.0.0.1:3470", "http://127.0.0.1:3471")
    assert owned_origin("http://127.0.0.1:65535") == "http://127.0.0.1:65535"


@pytest.mark.parametrize(
    "value",
    [
        None,
        3470,
        "https://127.0.0.1:3470",
        "http://localhost:3470",
        "http://[::1]:3470",
        "http://127.0.0.2:3470",
        "http://127.0.0.1.attacker.invalid:3470",
        "http://u:p@127.0.0.1:3470",
        "http://127.0.0.1:3470/",
        "http://127.0.0.1:3470/path",
        "http://127.0.0.1:3470?q=1",
        "http://127.0.0.1:3470#part",
        "http://127.0.0.1",
        "http://127.0.0.1:0",
        "http://127.0.0.1:80",
        "http://127.0.0.1:65536",
        "http://127.0.0.1:-1",
        "http://127.0.0.1:1e3",
        "http://127.0.0.1:03470",
        " http://127.0.0.1:3470",
    ],
)
def test_invalid_origin_rejected_without_input_echo(value: object) -> None:
    with pytest.raises(ValueError, match="^invalid owned local origin$"):
        owned_origin(value)


def test_registration_requires_private_input_and_both_origins(tmp_path: Path) -> None:
    path = tmp_path / "window.json"
    path.write_text(json.dumps({"web_origin": "http://127.0.0.1:3470"}))
    path.chmod(0o600)
    with pytest.raises(ValueError, match="invalid owned local origin"):
        registered_origins(tmp_path)
    path.chmod(0o644)
    with pytest.raises(ValueError):
        registered_origins(tmp_path)
