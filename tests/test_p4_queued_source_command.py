"""Queued native parent must carry one verified source root; legacy argv stays unchanged."""

import sys
from pathlib import Path
from typing import Any

import pytest
from commerceops.entrypoints.feishu_business import native_child_command

pytestmark = pytest.mark.offline


def test_legacy_native_child_keeps_original_module_argv() -> None:
    assert native_child_command("commerceops.entrypoints.feishu_worker_child") == [
        sys.executable,
        "-m",
        "commerceops.entrypoints.feishu_worker_child",
    ]


def test_queued_native_child_without_bound_source_rejects_before_spawn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delattr(sys, "_p4_queued_source_binding", raising=False)
    with pytest.raises(PermissionError, match="P4_QUEUED_SEALED_SOURCE_REQUIRED"):
        native_child_command("commerceops.entrypoints.feishu_worker_child", queued=True)


@pytest.mark.parametrize("change", ["none", "cwd", "python", "loaded_origin"])
def test_queued_child_uses_the_same_prechecked_command_and_source(
    change: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checked: list[bool] = []

    def check() -> None:
        checked.append(True)
        if change == "loaded_origin":
            raise PermissionError("P4A_IMPORT_ORIGIN")

    context: dict[str, Any] = dict(
        root=Path.cwd() / "other" if change == "cwd" else Path.cwd(),
        python=Path("/wrong/python") if change == "python" else Path(sys.executable),
        command=["/sealed/python", "-I", "-S", "-c", "stdlib bootstrap", "/sealed/manifest", "a"],
        check_loaded=check,
    )
    monkeypatch.setattr(sys, "_p4_queued_source_binding", context, raising=False)
    if change == "none":
        assert native_child_command("commerceops.entrypoints.feishu_worker_child", queued=True) == [
            *context["command"],
            "--module",
            "commerceops.entrypoints.feishu_worker_child",
        ]
    else:
        with pytest.raises(PermissionError):
            native_child_command("commerceops.entrypoints.feishu_worker_child", queued=True)
    assert checked == [True]
