"""Real httpx CookieJar snapshots without transport or owned resources."""

import copy

import httpx
import pytest

from .http_probe import snapshot_cookies


def test_real_httpx_cookiejar_cannot_be_deepcopied() -> None:
    with httpx.Client(trust_env=False) as client:
        with pytest.raises(TypeError, match="cannot pickle.*RLock"):
            copy.deepcopy(client.cookies.jar)
        assert list(snapshot_cookies(client.cookies).jar) == []


def test_cookie_snapshot_preserves_attributes_and_survives_active_replacement() -> None:
    with httpx.Client(trust_env=False) as client:
        response = httpx.Response(
            200,
            request=httpx.Request("GET", "https://demo.example.test/api/v4/demo/bootstrap"),
            headers=[
                (
                    "Set-Cookie",
                    "session=bootstrap; Domain=.example.test; Path=/api/v4/demo; "
                    "Secure; HttpOnly; SameSite=Strict; Expires=Wed, 01 Jan 2031 00:00:00 GMT",
                ),
                ("Set-Cookie", "session=other-path; Path=/other; SameSite=Lax"),
            ],
        )
        client.cookies.extract_cookies(response)
        originals = list(client.cookies.jar)
        assert len(originals) == 2
        snapshot = snapshot_cookies(client.cookies)
        saved = list(snapshot.jar)
        assert snapshot.jar is not client.cookies.jar
        assert [vars(c) for c in saved] == [vars(c) for c in originals]
        assert all(
            a is not b and vars(a)["_rest"] is not vars(b)["_rest"]
            for a, b in zip(saved, originals, strict=True)
        )
        assert saved[0].domain == ".example.test"
        assert saved[0].path == "/api/v4/demo"
        assert saved[0].secure and saved[0].expires is not None
        assert saved[0].has_nonstandard_attr("HttpOnly")
        assert saved[0].get_nonstandard_attr("SameSite") == "Strict"

        expected = [copy.deepcopy(vars(c)) for c in saved]
        originals[0].value = "mutated-active"
        originals[0].set_nonstandard_attr("SameSite", "None")
        client.cookies = httpx.Cookies()
        client.cookies.set("session", "post-cookie", domain="demo.example.test", path="/")
        assert [vars(c) for c in snapshot.jar] == expected

        client.cookies = snapshot_cookies(snapshot)
        assert [vars(c) for c in client.cookies.jar] == expected
        active = list(client.cookies.jar)
        active[0].value = "mutated-restored"
        active[0].set_nonstandard_attr("SameSite", "None")
        assert [vars(c) for c in snapshot.jar] == expected


def test_fresh_bootstrap_owner_with_same_cookie_name_retains_old_snapshot() -> None:
    with httpx.Client(trust_env=False) as client:
        client.cookies.set("bootstrap", "old-owner", domain="127.0.0.1", path="/api/v4/demo")
        old_cookie = snapshot_cookies(client.cookies)
        client.cookies.set("bootstrap", "new-owner", domain="127.0.0.1", path="/api/v4/demo")
        new_cookie = snapshot_cookies(client.cookies)
        # Cookies iteration yields equal names; owner identity requires Cookie values.
        assert list(old_cookie) == list(new_cookie) == ["bootstrap"]
        assert [(c.name, c.value) for c in old_cookie.jar] == [("bootstrap", "old-owner")]
        assert [(c.name, c.value) for c in new_cookie.jar] == [("bootstrap", "new-owner")]
        client.cookies = snapshot_cookies(old_cookie)
        assert client.cookies.get("bootstrap") == "old-owner"
        client.cookies.set("bootstrap", "later-owner", domain="127.0.0.1", path="/api/v4/demo")
        assert old_cookie.get("bootstrap") == "old-owner"
        assert new_cookie.get("bootstrap") == "new-owner"
