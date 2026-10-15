"""P4专用合成fixture及HTTP transport；业务/授权/ledger/恢复全部调用原生实现。"""

import asyncio
import json
import os
import subprocess
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
from commerceops.adapters.feishu.business_config import BusinessSettings
from commerceops.application.feishu_business.contracts import BASE_FIELDS
from commerceops.application.feishu_business.worker_window import ControlledWorkerWindow
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.web_config import WebConfig

from scripts.p4_acceptance import (
    CONTRACT,
    Deadline,
    bound_bytes,
    digest,
    materialize_entry,
    require,
    source_manifest,
    write_private,
)
from tests.p3_support import P3Fixture, initialize_p3


def reference(path: Path) -> dict[str, str]:
    return {"path": str(path.absolute()), "sha256": digest(bound_bytes(path, private=True))}


class FakeHTTPTransport:
    """只替换httpx最底层request；官方Factory/Client/request/ledger/adapter保持原生。"""

    def __init__(self, path: Path, settings: BusinessSettings):
        self.path, self.settings, self.calls = path, settings, 0

    def state(self) -> dict[str, Any]:
        return json.loads(bound_bytes(self.path, private=True))  # type: ignore[no-any-return]

    async def request(self, method: str, url: str, **kwargs: Any) -> Any:
        require(urlsplit(url).hostname == "open.feishu.cn", "P4A_FAKE_HOST")
        path = urlsplit(url).path
        state = self.state()
        self.calls += 1
        status = 200
        body: dict[str, Any] = {"code": 0}
        if path == "/open-apis/auth/v3/tenant_access_token/internal" and method == "POST":
            body.update(tenant_access_token=str(uuid4()), expire=7200)
        elif path == "/open-apis/bot/v3/info" and method == "GET":
            body["bot"] = {"open_id": self.settings.bot_open_id}
        elif path.endswith("/tables") and method == "GET":
            body["data"] = {
                "items": [{"table_id": "synthetic-table", "name": self.settings.base_table_name}],
                "total": 1,
                "has_more": False,
            }
        elif path.endswith("/fields") and method == "GET":
            body["data"] = {
                "items": [
                    {"field_name": name, "type": 2 if name in ("Quantity", "SyncVersion") else 1}
                    for name in BASE_FIELDS
                ],
                "total": 15,
                "has_more": False,
            }
        elif path == "/open-apis/im/v1/messages" and method == "POST":
            body["data"] = {
                "message_id": "synthetic-" + uuid4().hex,
                "chat_id": kwargs["json"]["receive_id"],
            }
        elif "/tables/synthetic-table/records" in path:
            behavior = state.get("behavior", "normal")
            if behavior == "timeout":
                raise httpx.ReadTimeout("synthetic timeout")
            if method == "GET":
                delay = state.get("read_delay_seconds", 0)
                require(type(delay) in (int, float) and 0 <= delay <= 1, "P4A_FAKE_DELAY")
                if delay:
                    await asyncio.sleep(delay)
                rows = json.loads(json.dumps(state["rows"]))
                if behavior == "partial":
                    rows = [{"record_id": "synthetic-partial", "fields": {"SKU": "synthetic"}}]
                elif behavior == "missing_required":
                    require(bool(rows), "P4A_FAKE_ROW_REQUIRED")
                    del rows[0]["fields"]["SKU"]
                elif behavior == "duplicate":
                    duplicate = json.loads(json.dumps(rows[0]))
                    duplicate["record_id"] = "synthetic-duplicate"
                    rows.append(duplicate)
                elif behavior == "wrong_content":
                    require(bool(rows), "P4A_FAKE_ROW_REQUIRED")
                    rows[0]["fields"]["SKU"] = "synthetic-wrong"
                elif behavior == "numeric_string":
                    for row in rows:
                        for key in ("Quantity", "SyncVersion"):
                            row["fields"][key] = str(row["fields"][key])
                elif behavior == "nullable_omitted":
                    for row in rows:
                        for key in ("ResolutionReason", "ResolvedBy", "ResolvedAt"):
                            if row["fields"].get(key) is None:
                                row["fields"].pop(key, None)
                elif behavior in ("bool_number", "float_number"):
                    for row in rows:
                        row["fields"]["Quantity"] = (
                            True if behavior == "bool_number" else float(row["fields"]["Quantity"])
                        )
                data: dict[str, Any] = {"items": rows, "total": len(rows), "has_more": False}
                if behavior == "pagination_cycle":
                    data.update(has_more=True, page_token="synthetic-cycle")  # noqa: S106
                body["data"] = data
            elif method == "POST":
                record = {
                    "record_id": "synthetic-" + uuid4().hex,
                    "fields": kwargs["json"]["fields"],
                }
                state["rows"].append(record)
                write_private(self.path, state)
                # 外端确已保存，回包缺record ACK；ledger仍真实记录HTTP200/code0。
                body["data"] = {} if behavior == "ack_drop" else {"record": record}
            elif method == "PUT":
                record_id = path.rsplit("/", 1)[1]
                matches = [r for r in state["rows"] if r["record_id"] == record_id]
                require(len(matches) == 1, "P4A_FAKE_UPDATE_TARGET")
                matches[0]["fields"] = kwargs["json"]["fields"]
                write_private(self.path, state)
                body["data"] = {"record": matches[0]}
            else:
                require(False, "P4A_FAKE_METHOD")
        else:
            require(False, "P4A_FAKE_REQUEST")
        return SimpleNamespace(status_code=status, headers={}, content=json.dumps(body).encode())

    @contextmanager
    def installed(self) -> Iterator[None]:
        original_async, original_sync = httpx.AsyncClient.request, httpx.Client.request
        transport = self

        async def request(client: Any, method: str, url: str, **kwargs: Any) -> Any:
            return await transport.request(method, str(url), **kwargs)

        def deny(*args: Any, **kwargs: Any) -> Any:
            require(False, "P4A_SYNC_NETWORK_DENIED")

        async_class: Any = httpx.AsyncClient
        sync_class: Any = httpx.Client
        async_class.request = request
        sync_class.request = deny
        try:
            yield
        finally:
            async_class.request, sync_class.request = original_async, original_sync


@dataclass
class PinnedProcess:
    process: subprocess.Popen[bytes]
    request: dict[str, Any]
    request_file: Path
    confirmed: bool = False
    lifecycle_not_started: bool = False

    @classmethod
    def start(cls, entry: Path, manifest_file: Path, request: dict[str, Any]) -> "PinnedProcess":
        manifest = json.loads(bound_bytes(manifest_file, private=True))
        directory = Path(request["output_file"]).parent
        request_file = directory / ("request-" + uuid4().hex + ".json")
        write_private(request_file, request)
        environment = {
            name: os.environ[name] for name in ("PATH", "SYSTEMROOT") if name in os.environ
        }
        environment.update(
            HOME=str(directory), TMPDIR=str(directory), LANG="C.UTF-8", LANGSMITH_TRACING="false"
        )
        process = subprocess.Popen(
            [
                manifest["python"],
                "-I",
                str(entry),
                "--manifest",
                str(manifest_file),
                "--manifest-sha256",
                digest(bound_bytes(manifest_file, private=True)),
                "--request",
                str(request_file),
                "--request-sha256",
                digest(bound_bytes(request_file, private=True)),
            ],
            cwd=manifest["root"],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        return cls(process, request, request_file)

    def wait(self, *, timeout: float = 45) -> dict[str, Any]:
        try:
            self.process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.communicate(timeout=5)
            raise TimeoutError("P4A_CHILD_TIMEOUT") from None
        output = Path(self.request["output_file"])
        require(output.is_file(), "P4A_CHILD_RESULT_REQUIRED")
        value: dict[str, Any] = json.loads(bound_bytes(output, private=True))
        require(self.process.returncode == value["exit_code"], "P4A_CHILD_EXIT_DISAGREEMENT")
        return value

    def terminate(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
        try:
            self.process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.communicate(timeout=5)


def worker_request(
    config: WebConfig,
    business: BusinessSettings,
    window: ControlledWorkerWindow,
    directory: Path,
    external: Path,
) -> dict[str, Any]:
    key = uuid4().hex
    config_file, business_file, window_file = (
        directory / (n + "-" + key + ".json") for n in ("web", "business", "window")
    )
    # WebConfig真正使用的私有输入另存新ref；不包含cookie/nonce的业务值。
    original = business.web_config_file
    config_value = json.loads(bound_bytes(original, private=True))
    write_private(config_file, config_value)
    business = business.model_copy(update={"web_config_file": config_file})
    write_private(business_file, business.model_dump(mode="json"))
    write_private(window_file, window.model_dump(mode="json"))
    require(config.database.user == "commerceops_app", "P4A_ROLE")
    external_refs = {"external_records": reference(external)}
    if window.terminal_update is not None:
        control = directory / ("terminal-http-" + key + ".json")
        write_private(
            control,
            dict(
                contract="p4-terminal-lab-http-v1",
                state_path=str(external),
                database=config.database.name,
                organization_id=str(window.organization_id),
                window_id=str(window.window_id),
            ),
        )
        external_refs = {"external_transport": reference(control)}
    return {
        "contract": CONTRACT,
        "action": "worker",
        "transport": "fake",
        "private_refs": {
            "web_config": reference(config_file),
            "business": reference(business_file),
            "window": reference(window_file),
            **external_refs,
        },
        "output_file": str(directory / ("worker-result-" + key + ".json")),
    }


@dataclass
class AcceptanceFixture:
    fixture: P3Fixture
    business: BusinessSettings
    entry: Path
    manifest_file: Path
    external: Path
    deadline: Deadline
    case_kind: str
    expected_item_count: int
    expected_quantity_total: str
    processes: list[PinnedProcess]

    @classmethod
    def prepare(
        cls,
        owner: DatabaseSettings,
        app: DatabaseSettings,
        directory: Path,
        deadline: Deadline,
        *,
        case_kind: str,
        entry_manifest_ref: Mapping[str, str] | None = None,
    ) -> "AcceptanceFixture":
        from commerceops.entrypoints.api import create_app
        from commerceops.infrastructure.replenishment_repository import ReplenishmentStore
        from fastapi.testclient import TestClient

        from tests.inventory_support import DIRECTORY
        from tests.p3_support import ORIGIN
        from tests.p4_recovery_support import settings
        from tests.test_p4_gateway_pg import service

        require(case_kind in ("recover_single_item", "batch_twenty_items"), "P4A_FIXTURE_CASE")
        count, total = (1, "70") if case_kind == "recover_single_item" else (20, "2000")
        directory.chmod(0o700)
        app = app.model_copy(update={"runtime_password_file": None})
        f = initialize_p3(owner, app, directory)
        # 新合成部署显式用原支持1..30s的scan knob；审批/会话/原SDK期限均不改。
        f.config = replace(f.config, recovery_scan_seconds=1)
        config_value = json.loads(bound_bytes(f.config_file, private=True))
        config_value["recovery_scan_seconds"] = 1
        write_private(f.config_file, config_value)
        f.client.close()
        f.store = ReplenishmentStore(f.config, DIRECTORY)
        f.client = TestClient(
            create_app(web_config=f.config, replenishment_store=f.store), base_url=ORIGIN
        )
        service(f)  # 仅本轮新合成Feishu身份，随后重登取得最终auth_version。
        f.relogin()
        secret, base_ref = directory / "dummy-app-material", directory / "dummy-base-material"
        # dummy材料也用原Factory私有文件读取边界；不是旧AppSecret/平台token。
        for path in (secret, base_ref):
            path.write_text("synthetic-" + uuid4().hex)
            path.chmod(0o600)
        business = settings(f).model_copy(
            update={
                "app_secret_file": secret,
                "base_app_token_file": base_ref,
            }
        )
        external = directory / "external-records.json"
        write_private(external, {"behavior": "partial" if count == 1 else "ack_drop", "rows": []})
        root = Path(__file__).resolve().parents[1]
        if entry_manifest_ref is None:
            # 独立PG回归自行准备其唯一entry；完整outer必须显式传既有冻结context。
            entry = materialize_entry(directory)
            manifest_file = directory / "source-manifest.json"
            write_private(manifest_file, source_manifest(root, entry))
        else:
            manifest_file = Path(entry_manifest_ref["path"])
            manifest = json.loads(
                bound_bytes(manifest_file, entry_manifest_ref["sha256"], private=True)
            )
            entry = Path(manifest["entry"])
            bound_bytes(entry, manifest["entry_sha256"], private=True)
            require(manifest["root"] == str(root), "P4A_CWD")
        write_private(directory / "app-database.json", app.model_dump(mode="json"))
        write_private(
            directory / "web-credentials.json",
            {"login": f.login, "password": f.password.get_secret_value()},
        )
        return cls(
            f, business, entry, manifest_file, external, deadline, case_kind, count, total, []
        )

    def save_continuation(self, origin: Mapping[str, Any]) -> dict[str, str]:
        path = self.fixture.private / "continuation.json"
        write_private(
            path,
            dict(
                config=reference(self.fixture.config_file),
                business=self.business.model_dump(mode="json"),
                entry=str(self.entry),
                manifest=reference(self.manifest_file),
                external=str(self.external),
                seed=asdict(self.fixture.inventory.data),
                session=self.fixture.client.cookies.get("commerceops_session"),
                credentials=reference(self.fixture.private / "web-credentials.json"),
                case_kind=self.case_kind,
                origin_gateway=origin["origin_gateway"].model_dump(mode="json"),
                origin_window=origin["origin_window"].model_dump(mode="json"),
                origin_owner=origin["origin_owner"],
            ),
        )
        return reference(path)

    @classmethod
    def restore(cls, ref: Mapping[str, str], deadline: Deadline) -> tuple["AcceptanceFixture", Any]:
        """只重开本轮fixture对象/连接；不seed、不登录、不arm，不构造业务行。"""
        from commerceops.application.commerce.analysis_task import TrustedReadIdentity
        from commerceops.application.feishu_business.gateway_window import GatewayWindow
        from commerceops.entrypoints.api import create_app
        from commerceops.infrastructure.replenishment_repository import ReplenishmentStore
        from commerceops.infrastructure.web_sessions import SessionStore
        from fastapi.testclient import TestClient
        from pydantic import SecretStr

        from tests.inventory_support import DIRECTORY, InventoryFixture
        from tests.pg_support import Seed

        value = json.loads(bound_bytes(Path(ref["path"]), ref["sha256"], private=True))
        cfg = value["config"]
        bound_bytes(Path(cfg["path"]), cfg["sha256"], private=True)
        config = WebConfig.from_file(Path(cfg["path"]))
        require(config.database.user == "commerceops_app", "P4A_ROLE")
        actor = SessionStore(config).authenticate(value["session"])
        data = dict(value["seed"])
        for key in ("organization", "shop", "principal", "conversation", "task"):
            data[key] = UUID(data[key])
        seed = Seed(**data)
        with connect(config.database) as db:
            identity = db.execute(
                "SELECT id FROM business.identities WHERE principal_id=%s AND provider='feishu'",
                (actor.principal_id,),
            ).fetchone()
        require(identity is not None, "P4A_HISTORY_REQUIRED")
        assert identity is not None
        inventory = InventoryFixture(
            config.database,
            config.database,
            seed,
            TrustedReadIdentity(
                identity["id"],
                actor.principal_id,
                actor.organization_id,
                seed.shop,
                actor.auth_version,
            ),
        )
        store = ReplenishmentStore(config, DIRECTORY)
        client = TestClient(create_app(web_config=config, replenishment_store=store))
        client.cookies.set("commerceops_session", value["session"])
        credential_ref = value["credentials"]
        credentials = json.loads(
            bound_bytes(Path(credential_ref["path"]), credential_ref["sha256"], private=True)
        )
        f = P3Fixture(
            inventory,
            config,
            store,
            client,
            actor,
            Path(cfg["path"]),
            Path(ref["path"]).parent,
            credentials["login"],
            SecretStr(credentials["password"]),
        )
        business = BusinessSettings.model_validate_json(json.dumps(value["business"]))
        manifest = value["manifest"]
        bound_bytes(Path(manifest["path"]), manifest["sha256"], private=True)
        single = value["case_kind"] == "recover_single_item"
        a = cls(
            f,
            business,
            Path(value["entry"]),
            Path(manifest["path"]),
            Path(value["external"]),
            deadline,
            value["case_kind"],
            1 if single else 20,
            "70" if single else "2000",
            [],
        )
        value["origin_gateway"] = GatewayWindow.model_validate_json(
            json.dumps(value["origin_gateway"])
        )
        value["origin_window"] = ControlledWorkerWindow.model_validate_json(
            json.dumps(value["origin_window"])
        )
        return a, value

    def start(self, request: dict[str, Any]) -> PinnedProcess:
        self.deadline.remaining()
        request["runtime"] = {
            "deadline_utc": self.deadline.expires_at.isoformat(),
            "monotonic_end": self.deadline.monotonic_end,
            "cleanup_reserve_seconds": self.deadline.reserve,
        }
        child = PinnedProcess.start(self.entry, self.manifest_file, request)
        self.processes.append(child)
        return child

    def gateway(self, *, workflows: int = 0, seconds: int = 240) -> tuple[Any, PinnedProcess]:
        from tests.p4_recovery_support import gateway

        f = self.fixture
        case = "known_inbound" if self.case_kind == "recover_single_item" else "baseline"
        remaining = self.deadline.remaining()
        require(remaining > 65, "P4A_GATEWAY_CAPACITY")
        window = gateway(
            f, case=case, seconds=min(seconds, int(remaining) - 1), max_workflows=workflows
        )
        key = uuid4().hex
        business_file, window_file = (
            f.private / ("gateway-business-" + key + ".json"),
            f.private / ("gateway-window-" + key + ".json"),
        )
        write_private(business_file, self.business.model_dump(mode="json"))
        write_private(window_file, window.model_dump(mode="json"))
        ready = f.private / ("gateway-ready-" + key + ".json")
        child = self.start(
            {
                "contract": CONTRACT,
                "action": "gateway",
                "transport": "fake",
                "private_refs": {
                    "web_config": reference(f.config_file),
                    "business": reference(business_file),
                    "window": reference(window_file),
                },
                "output_file": str(f.private / ("gateway-result-" + key + ".json")),
                "ready_file": str(ready),
            }
        )
        end = time.monotonic() + min(15, self.deadline.remaining())
        while not ready.exists():
            require(child.process.poll() is None and time.monotonic() < end, "P4A_GATEWAY_READY")
            time.sleep(0.02)
        return window, child

    def stop_gateway(self, window: Any, child: PinnedProcess) -> None:
        from commerceops.entrypoints.feishu_business import confirm_gateway_child

        child.terminate()
        require(child.process.returncode == 0, "P4A_GATEWAY_EXIT")
        asyncio.run(
            confirm_gateway_child(
                self.fixture.config,
                self.fixture.actor.organization_id,
                window.window_id,
                child.process.pid,
                child.process.returncode,
            )
        )
        child.confirmed = True

    def worker(
        self,
        window: ControlledWorkerWindow,
        *,
        stop_after_verified: UUID | None = None,
        replay_of: PinnedProcess | None = None,
    ) -> tuple[PinnedProcess, dict[str, Any]]:

        f = self.fixture
        if replay_of is None:
            request = worker_request(f.config, self.business, window, f.private, self.external)
        else:
            # 冷重放绑定原始私有输入；仅结果文件名不同，不重新arm或改window。
            request = dict(replay_of.request)
            request["output_file"] = str(f.private / ("replay-" + uuid4().hex + ".json"))
        child = self.start(request)
        if stop_after_verified is not None:
            end = time.monotonic() + min(60, self.deadline.remaining())
            while True:
                with connect(f.config.database) as db:
                    row = db.execute(
                        "SELECT status FROM business.p4_base_deliveries WHERE outbox_id=%s",
                        (stop_after_verified,),
                    ).fetchone()
                if row and row["status"] == "verified":
                    child.process.terminate()
                    break
                require(
                    child.process.poll() is None and time.monotonic() < end,
                    "P4A_VERIFIED_DEADLINE",
                )
                time.sleep(0.05)
        value = child.wait(timeout=min(90, self.deadline.remaining()))
        self.confirm_worker(child, value)
        return child, value

    def confirm_worker(
        self, child: PinnedProcess, value: Mapping[str, Any], *, allow_no_start: bool = False
    ) -> None:
        from commerceops.entrypoints.feishu_business import confirm_worker_child

        require(child.process.returncode == value["exit_code"], "P4A_CHILD_EXIT_DISAGREEMENT")
        with connect(self.fixture.config.database) as db:
            starts = db.execute(
                "SELECT id FROM business.audit_events WHERE source='worker' AND action='started' "
                "AND organization_id=%s AND (after_state->>'pid')::bigint=%s",
                (self.fixture.actor.organization_id, child.process.pid),
            ).fetchall()
        if not starts:
            require(allow_no_start and value["exit_code"] == 1, "P4A_WORKER_STARTED")
            # 已wait/reap、实际0 started；此分支绝不补stopped/termination audit。
            child.lifecycle_not_started = True
            return
        require(len(starts) == 1, "P4A_WORKER_STARTED")
        asyncio.run(
            confirm_worker_child(
                self.fixture.config, self.fixture.actor.organization_id, child.process.pid
            )
        )
        child.confirmed = True

    def external_behavior(self, behavior: str) -> None:
        value = json.loads(bound_bytes(self.external, private=True))
        value["behavior"] = behavior
        write_private(self.external, value)

    def wait_due(self, outbox: UUID) -> None:
        end = time.monotonic() + min(65, self.deadline.remaining())
        while True:
            with connect(self.fixture.config.database) as db:
                row = db.execute(
                    "SELECT next_attempt_at<=clock_timestamp() AS due "
                    "FROM business.p4_base_deliveries WHERE outbox_id=%s",
                    (outbox,),
                ).fetchone()
            require(row is not None, "P4A_DELIVERY_REQUIRED")
            assert row is not None
            if row["due"]:
                return
            require(time.monotonic() < end, "P4A_BACKOFF_DEADLINE")
            time.sleep(0.1)

    def cleanup(self) -> bool:
        # 独立于业务snapshot，先收所有OS子进程，再按原确认器核生命周期。
        from commerceops.entrypoints.feishu_business import (
            confirm_gateway_child,
            confirm_worker_child,
        )

        good = True
        for child in self.processes:
            try:
                child.terminate()
                if child.confirmed or child.lifecycle_not_started:
                    continue
                if child.request["action"] == "worker":
                    asyncio.run(
                        confirm_worker_child(
                            self.fixture.config,
                            self.fixture.actor.organization_id,
                            child.process.pid,
                        )
                    )
                elif child.request["action"] == "gateway":
                    value = json.loads(
                        bound_bytes(
                            Path(child.request["private_refs"]["window"]["path"]), private=True
                        )
                    )
                    asyncio.run(
                        confirm_gateway_child(
                            self.fixture.config,
                            self.fixture.actor.organization_id,
                            UUID(value["window_id"]),
                            child.process.pid,
                            int(child.process.returncode),
                        )
                    )
                child.confirmed = True
            except Exception:
                good = False
        self.fixture.client.close()
        return good


def completed_origin(
    a: AcceptanceFixture,
) -> tuple[Any, ControlledWorkerWindow, str, dict[str, Any]]:
    """原T1/Graph/Feishu审批/20items；官方Factory+真实ledger，HTTP partial产生C0。"""
    from commerceops.adapters.feishu.business_gateway import BusinessCard
    from commerceops.application.feishu_business.worker_window import GROUP20_CAPS, KNOWN70_CAPS
    from commerceops.application.replenishment.contracts import DecisionInput
    from commerceops.infrastructure.approval_decisions import nonce_for
    from commerceops.infrastructure.feishu_gateway_window import guard_gateway

    from tests.test_p4_gateway_pg import message, service

    f = a.fixture
    single = a.case_kind == "recover_single_item"
    old, gateway_child = a.gateway(workflows=1 if single else 2)
    worker: PinnedProcess | None = None
    try:
        intake = service(
            f,
            case="known_inbound" if single else "baseline",
            allow_live_bindings=True,
            gateway_guard=lambda db, create: guard_gateway(db, old, create),
        )
        incoming = message(f, kind="p2p" if single else "group")
        task = UUID(intake.message(incoming)["task_id"])
        window = ControlledWorkerWindow.model_validate_json(
            json.dumps(
                {
                    "schema_version": "p4-worker-v1",
                    "window_id": str(uuid4()),
                    "gateway_window_id": str(old.window_id),
                    "organization_id": str(f.actor.organization_id),
                    "shop_id": str(f.inventory.data.shop),
                    "task_ids": [str(task)],
                    "expires_at": (datetime.now(UTC) + timedelta(seconds=60)).isoformat(),
                    "enabled": True,
                    "profile": "known70" if single else "group20",
                    "caps": dict(KNOWN70_CAPS if single else GROUP20_CAPS),
                }
            )
        )
        worker = a.start(worker_request(f.config, a.business, window, f.private, a.external))
        end = time.monotonic() + min(80, a.deadline.remaining())
        while True:
            with connect(f.config.database) as db:
                approval = db.execute(
                    "SELECT * FROM business.approvals WHERE task_id=%s", (task,)
                ).fetchone()
                binding = (
                    None
                    if not approval
                    else db.execute(
                        "SELECT message_id,chat_id FROM business.p4_card_bindings "
                        "WHERE approval_id=%s",
                        (approval["id"],),
                    ).fetchone()
                )
                plan = (
                    None
                    if not approval
                    else db.execute(
                        "SELECT content FROM business.replenishment_plans WHERE id=%s",
                        (approval["plan_id"],),
                    ).fetchone()
                )
                progress = {
                    "approval_exists": approval is not None,
                    "approval_ready": bool(approval and approval["ready_at"]),
                    "IM_binding_exists": binding is not None,
                    "task_states": db.execute(
                        "SELECT state,failure_code FROM business.business_tasks WHERE id=%s "
                        "OR id=(SELECT source_task_id FROM business.p3_task_sources "
                        "WHERE task_id=%s) "
                        "ORDER BY kind",
                        (task, task),
                    ).fetchall(),
                    "jobs": db.execute(
                        "SELECT status,attempts FROM business.jobs WHERE task_id=%s OR task_id="
                        "(SELECT source_task_id FROM business.p3_task_sources WHERE task_id=%s) "
                        "ORDER BY kind",
                        (task, task),
                    ).fetchall(),
                    "outbox": db.execute(
                        "SELECT operation,status,source_mode,sender_enabled,count(*) AS n "
                        "FROM business.outbox WHERE task_id=%s GROUP BY "
                        "operation,status,source_mode,sender_enabled ORDER BY operation",
                        (task,),
                    ).fetchall(),
                    "IM": db.execute(
                        "SELECT status,count(*) AS n FROM business.p4_im_deliveries "
                        "WHERE task_id=%s GROUP BY status",
                        (task,),
                    ).fetchall(),
                }
            write_private(f.private / "origin-progress.safe.json", progress)
            if approval and approval["ready_at"] and binding and plan:
                break
            require(worker.process.poll() is None and time.monotonic() < end, "P4A_APPROVAL_READY")
            time.sleep(0.05)
        request = DecisionInput.model_validate(
            dict(
                schema_version="p3-web-v1",
                request_key=uuid4(),
                approval_id=approval["id"],
                plan_id=approval["plan_id"],
                plan_version=approval["plan_version"],
                plan_hash=approval["plan_hash"],
                action="approve_with_assumptions"
                if plan["content"]["required_assumptions"]
                else "approve",
                nonce=nonce_for(f.config, approval),
                acknowledged_assumption_keys=tuple(
                    v["key"] for v in plan["content"]["required_assumptions"]
                ),
            )
        )
        intake.card(
            BusinessCard(
                "synthetic-" + uuid4().hex,
                incoming.identity,
                binding["chat_id"],
                binding["message_id"],
                request,
            )
        )
        result = worker.wait(timeout=min(45, a.deadline.remaining()))
        from commerceops.entrypoints.feishu_business import confirm_worker_child

        asyncio.run(confirm_worker_child(f.config, f.actor.organization_id, worker.process.pid))
        worker.confirmed = True
        require(worker.process.returncode == 1, "P4A_ORIGIN_EXPECTED_UNKNOWN")
        with connect(f.config.database) as db:
            delivery = db.execute(
                "SELECT d.*,o.request_hash FROM business.p4_base_deliveries d "
                "JOIN business.outbox o ON o.id=d.outbox_id WHERE d.task_id=%s "
                "AND d.status='unknown'",
                (task,),
            ).fetchall()
            total = db.execute(
                "SELECT count(*) AS n,sum(quantity)::text AS quantity "
                "FROM business.replenishment_items WHERE task_id=%s",
                (task,),
            ).fetchone()
        require(len(delivery) == 1 and delivery[0]["attempts"] == 1, "P4A_ORIGIN_UNKNOWN_REQUIRED")
        if single:
            require(delivery[0]["last_error"] == "INCOMPLETE_READBACK", "P4A_C0_REQUIRED")
        require(
            total == {"n": a.expected_item_count, "quantity": a.expected_quantity_total},
            "P4A_FIXTURE_CARDINALITY",
        )
        owner = result["pg_proof"]["worker_owner"]
        return old, window, owner, delivery[0]
    finally:
        if worker is not None and worker.process.poll() is None:
            worker.terminate()
        a.stop_gateway(old, gateway_child)


def sender_manifest(
    a: AcceptanceFixture,
    old: Any,
    new: Any,
    original: ControlledWorkerWindow,
    owner: str,
    delivery: Mapping[str, Any],
) -> ControlledWorkerWindow:
    from commerceops.application.feishu_business.worker_window import FIRST_CREATE_CAPS

    from tests.test_p4_a09_workflow_pg import manifest

    f = a.fixture
    recovered = manifest(f, old, new, next(iter(original.task_ids)), owner, original.window_id)
    value = recovered.model_dump(mode="json")
    value.update(
        profile="approved_first_create",
        caps=dict(FIRST_CREATE_CAPS),
        first_create={
            k: str(delivery[k]) if k in ("outbox_id", "item_id", "client_token") else delivery[k]
            for k in (
                "outbox_id",
                "item_id",
                "client_token",
                "version",
                "projection_hash",
                "request_hash",
            )
        },
    )
    return ControlledWorkerWindow.model_validate_json(json.dumps(value))


def prepare_single_ro(
    a: AcceptanceFixture, *, concurrent_once: bool = False, defer_explicit: bool = False
) -> dict[str, Any]:
    """实际原生C0、sender、reader、explicit once及完全相同输入的冷重放。"""
    from scripts.p4_acceptance import QUERIES

    require(a.case_kind == "recover_single_item", "P4A_FIXTURE_CASE")
    gateways: list[tuple[Any, PinnedProcess]] = []
    try:
        old, origin, owner, delivery = completed_origin(a)
        remaining = (origin.expires_at - datetime.now(UTC)).total_seconds()
        require(remaining < 61, "P4A_ORIGIN_WINDOW")
        if remaining > 0:
            time.sleep(remaining + 0.02)
        a.wait_due(delivery["outbox_id"])
        sender_gateway, child = a.gateway(seconds=30 if defer_explicit else 240)
        gateways.append((sender_gateway, child))
        sender = sender_manifest(a, old, sender_gateway, origin, owner, delivery)
        a.external_behavior("ack_drop")
        _, sent = a.worker(sender)
        require(
            sent["exit_code"] == 1 and sent["stages"]["CALL"]["state"] == "PASSED",
            "P4A_SENDER_EXPECTED_UNKNOWN",
        )
        a.stop_gateway(sender_gateway, child)
        a.wait_due(delivery["outbox_id"])
        reader_gateway, child = a.gateway(seconds=30 if defer_explicit else 240)
        gateways.append((reader_gateway, child))
        reader = recovery_manifest(a, sender, sent["pg_proof"]["worker_owner"], reader_gateway)
        a.external_behavior("missing_required")
        _, read = a.worker(reader)
        require(read["exit_code"] == 1, "P4A_READER_EXPECTED_INCOMPLETE")
        a.stop_gateway(reader_gateway, child)
        a.wait_due(delivery["outbox_id"])
        if defer_explicit:
            # 独立LAB历史进程退出后，真实outer才从PG派生reader/arm；不预消费once。
            return dict(
                origin_gateway=old,
                origin_window=origin,
                origin_owner=owner,
                delivery=delivery,
                prior_reader=reader,
                reader_result=read,
            )
        current_gateway, child = a.gateway()
        gateways.append((current_gateway, child))
        current = recheck_manifest(a, reader, read["pg_proof"]["worker_owner"], current_gateway)
        a.external_behavior("normal")
        race: dict[str, Any] | None = None
        if concurrent_once:
            state = json.loads(bound_bytes(a.external, private=True))
            state["read_delay_seconds"] = 1
            write_private(a.external, state)
            first = a.start(
                worker_request(a.fixture.config, a.business, current, a.fixture.private, a.external)
            )
            second_request = dict(first.request)
            second_request["output_file"] = str(a.fixture.private / "concurrent-second.json")
            second = a.start(second_request)
            pairs = [(c, c.wait(timeout=min(90, a.deadline.remaining()))) for c in (first, second)]
            for c, v in pairs:
                a.confirm_worker(c, v, allow_no_start=True)
            winners = [(c, v) for c, v in pairs if v["exit_code"] == 0]
            losers = [(c, v) for c, v in pairs if v["exit_code"] == 1]
            require(len(winners) == len(losers) == 1, "P4A_CONCURRENT_ONCE")
            verified_child, verified = winners[0]
            require(
                losers[0][1]["stages"]["PREFLIGHT"]["state"] == "NOT_RUN",
                "P4A_CONCURRENT_SDK_STARTED",
            )
            race = dict(
                actual_child_exits=[v["exit_code"] for _, v in pairs],
                same_window_and_private_refs=True,
                no_start_count=sum(c.lifecycle_not_started for c, _ in pairs),
                expected_rejections=1,
            )
        else:
            verified_child, verified = a.worker(current)
        require(verified["exit_code"] == 0, "P4A_EXPLICIT_RO_UNVERIFIED")
        with connect(a.fixture.config.database) as db:
            before = QUERIES["SDK_COUNTS"].execute(
                db, (current.window_id,), revision="0016", role="app"
            )
            links = QUERIES["LINKS"].execute(
                db, (delivery["item_id"],), revision="0016", role="app"
            )
            rows = QUERIES["ITEMS"].execute(
                db, (next(iter(current.task_ids)),), revision="0016", role="app"
            )
        require(len(links) == 1 and len(rows) == 1, "P4A_SINGLE_ANCHOR")
        require(all(r["status"] == "open" for r in rows), "P4A_ITEM_CHANGED")
        require(
            sum(r["n"] for r in before if r["method"] == "bitable.v1.app_table_record.list") == 1,
            "P4A_RO_CALL_COUNT",
        )
        replay_child, replay = a.worker(current, replay_of=verified_child)
        require(
            replay["exit_code"] == 1
            and replay["stages"]["AUTHORIZE"]["state"] == "FAILED"
            and replay["stages"]["PREFLIGHT"]["state"] == "NOT_RUN",
            "P4A_REPLAY_NOT_DENIED",
        )
        with connect(a.fixture.config.database) as db:
            after = QUERIES["SDK_COUNTS"].execute(
                db, (current.window_id,), revision="0016", role="app"
            )
            once = db.execute(
                "SELECT action,count(*) AS n FROM business.audit_events "
                "WHERE action IN ('explicit_ro_recheck_authorized',"
                "'explicit_ro_recheck_dispatched') "
                "AND entity_id=%s GROUP BY action ORDER BY action",
                (str(delivery["outbox_id"]),),
            ).fetchall()
        require(before == after, "P4A_REPLAY_SDK_CHANGED")
        require(
            replay_child.request["private_refs"] == verified_child.request["private_refs"],
            "P4A_REPLAY_INPUT_CHANGED",
        )
        require(len(once) == 2 and all(r["n"] == 1 for r in once), "P4A_ONCE_COUNT")
        return dict(
            origin_gateway=old,
            origin_window=origin,
            origin_owner=owner,
            delivery=delivery,
            window=current,
            verified=verified,
            replay=replay,
            worker_pid=verified_child.process.pid,
            links=links,
            concurrent_once=race,
            replay_proof=dict(
                actual_child_exit=replay["exit_code"],
                authorization=replay["stages"]["AUTHORIZE"]["state"],
                preflight=replay["stages"]["PREFLIGHT"]["state"],
                original_private_refs_equal=True,
                native_sdk_counts_before=before,
                native_sdk_counts_after=after,
                native_once_events=once,
                sdk_counts_equal=before == after,
                reaped=all(c.process.returncode is not None for c in a.processes),
            ),
        )
    finally:
        for window, child in reversed(gateways):
            if not child.confirmed:
                a.stop_gateway(window, child)


def ordinary_manifest(
    a: AcceptanceFixture,
    old: Any,
    new: Any,
    original: ControlledWorkerWindow,
    owner: str,
    delivery: Mapping[str, Any],
) -> ControlledWorkerWindow:
    """20项只走原ordinary outbox RO；不借single first-create/explicit合同。"""
    from commerceops.application.feishu_business.worker_window import READONLY_RECOVERY_CAPS
    from commerceops.infrastructure.feishu_outbox_recovery import sdk_window_hash

    from tests.test_p4_a09_workflow_pg import manifest

    f = a.fixture
    base = manifest(f, old, new, next(iter(original.task_ids)), owner, original.window_id)
    history = base.workflow_recovery
    require(history is not None, "P4A_HISTORY_REQUIRED")
    assert history is not None
    with connect(f.config.database) as db:
        approval = db.execute(
            "SELECT * FROM business.approvals WHERE id=%s", (history.approval_id,)
        ).fetchone()
        sdk = db.execute(
            "SELECT * FROM business.p4_sdk_windows WHERE id=%s", (original.window_id,)
        ).fetchone()
    require(bool(approval and sdk), "P4A_HISTORY_REQUIRED")
    assert approval and sdk
    value = base.model_dump(mode="json")
    value.update(
        profile="approved_outbox", caps=dict(READONLY_RECOVERY_CAPS), workflow_recovery=None
    )
    value["recovery"] = dict(
        schema_version="p4-approved-outbox-v1",
        worker_window_id=value["window_id"],
        gateway_window_id=value["gateway_window_id"],
        expires_at=value["expires_at"],
        original_gateway_id=str(history.original_gateway_id),
        original_gateway_hash=history.original_gateway_hash,
        gateway_termination_id=str(history.gateway_termination_id),
        worker_owner=owner,
        worker_termination_id=str(history.worker_termination_id),
        original_sdk_window_id=str(original.window_id),
        original_sdk_window_hash=sdk_window_hash(sdk),
        task_id=str(history.task_id),
        task_version=history.task_version,
        inbox_id=str(history.inbox_id),
        receipt_hash=history.receipt_hash,
        plan_id=str(approval["plan_id"]),
        plan_version=approval["plan_version"],
        plan_hash=approval["plan_hash"],
        approval_id=str(approval["id"]),
        decision_id=str(approval["decision_id"]),
        execution_id=str(history.execution_id),
        operator_auth_version=history.operator_auth_version,
        approver_auth_version=approval["decided_auth_version"],
        target_key=a.business.base_target_key,
        projections=[
            {
                k: str(delivery[k])
                if k in ("outbox_id", "item_id", "client_token")
                else delivery[k]
                for k in (
                    "outbox_id",
                    "item_id",
                    "client_token",
                    "version",
                    "projection_hash",
                    "request_hash",
                )
            }
        ],
    )
    return ControlledWorkerWindow.model_validate_json(json.dumps(value))


def prepare_batch_ro(a: AcceptanceFixture) -> dict[str, Any]:
    require(a.case_kind == "batch_twenty_items", "P4A_FIXTURE_CASE")
    old, origin, owner, delivery = completed_origin(a)
    a.wait_due(delivery["outbox_id"])
    gateway, child = a.gateway()
    try:
        window = ordinary_manifest(a, old, gateway, origin, owner, delivery)
        a.external_behavior("normal")
        _, result = a.worker(window, stop_after_verified=delivery["outbox_id"])
        require(result["exit_code"] == 0, "P4A_BATCH_RO_UNVERIFIED")
        with connect(a.fixture.config.database) as db:
            items = db.execute(
                "SELECT id,status,quantity::text AS quantity "
                "FROM business.replenishment_items WHERE task_id=%s ORDER BY id",
                (next(iter(window.task_ids)),),
            ).fetchall()
        require(len(items) == 20 and all(r["status"] == "open" for r in items), "P4A_BATCH_ITEMS")
        return dict(
            window=window,
            verified=result,
            items=items,
            explicit_recheck=False,
            origin_gateway=old,
            origin_window=origin,
            origin_owner=owner,
            delivery=delivery,
        )
    finally:
        a.stop_gateway(gateway, child)


def recovery_manifest(
    a: AcceptanceFixture, sender: ControlledWorkerWindow, sender_owner: str, new: Any
) -> ControlledWorkerWindow:
    from commerceops.application.feishu_business.worker_window import READONLY_RECOVERY_CAPS
    from commerceops.domain.commerce_values import facts_hash
    from commerceops.infrastructure.feishu_outbox_recovery import receipt_hash, sdk_window_hash

    f = a.fixture
    origin = sender.workflow_recovery
    require(origin is not None and sender.first_create is not None, "P4A_SENDER_REQUIRED")
    assert origin is not None and sender.first_create is not None
    with connect(f.config.database) as db:
        approval = db.execute(
            "SELECT * FROM business.approvals WHERE id=%s", (origin.approval_id,)
        ).fetchone()
        receipt = db.execute(
            "SELECT r.*,i.payload_hash FROM business.p4_inbox_receipts r "
            "JOIN business.inbox_events i ON i.id=r.inbox_id WHERE r.inbox_id=%s",
            (origin.inbox_id,),
        ).fetchone()
        sdk = db.execute(
            "SELECT * FROM business.p4_sdk_windows WHERE id=%s", (sender.window_id,)
        ).fetchone()
        claim = db.execute(
            "SELECT after_state FROM business.audit_events WHERE id=%s", (sender.gateway_window_id,)
        ).fetchone()
        end = db.execute(
            "SELECT id FROM business.audit_events WHERE source='feishu_gateway' "
            "AND action='termination_confirmed' AND entity_id=%s",
            (str(sender.gateway_window_id),),
        ).fetchone()
        stopped = db.execute(
            "SELECT id FROM business.audit_events WHERE source='worker' "
            "AND action='termination_confirmed' AND entity_id=%s",
            (sender_owner,),
        ).fetchone()
    require(all((approval, receipt, sdk, claim, end, stopped)), "P4A_HISTORY_REQUIRED")
    assert approval and receipt and sdk and claim and end and stopped
    value = sender.model_dump(mode="json")
    value.update(
        window_id=str(uuid4()),
        gateway_window_id=str(new.window_id),
        expires_at=new.expires_at.isoformat(),
        profile="approved_outbox",
        caps=dict(READONLY_RECOVERY_CAPS),
        workflow_recovery=None,
        first_create=None,
    )
    value["recovery"] = dict(
        schema_version="p4-approved-outbox-v1",
        worker_window_id=value["window_id"],
        gateway_window_id=value["gateway_window_id"],
        expires_at=value["expires_at"],
        original_gateway_id=str(origin.original_gateway_id),
        original_gateway_hash=origin.original_gateway_hash,
        gateway_termination_id=str(origin.gateway_termination_id),
        worker_owner=sender_owner,
        worker_termination_id=str(stopped["id"]),
        original_sdk_window_id=str(sender.window_id),
        original_sdk_window_hash=sdk_window_hash(sdk),
        task_id=str(origin.task_id),
        task_version=origin.task_version,
        inbox_id=str(origin.inbox_id),
        receipt_hash=receipt_hash(receipt),
        plan_id=str(approval["plan_id"]),
        plan_version=approval["plan_version"],
        plan_hash=approval["plan_hash"],
        approval_id=str(approval["id"]),
        decision_id=str(approval["decision_id"]),
        execution_id=str(origin.execution_id),
        operator_auth_version=origin.operator_auth_version,
        approver_auth_version=approval["decided_auth_version"],
        target_key=a.business.base_target_key,
        projections=[sender.first_create.model_dump(mode="json")],
        sender_gateway={
            "gateway_id": str(sender.gateway_window_id),
            "gateway_hash": facts_hash(claim["after_state"]),
            "termination_id": str(end["id"]),
        },
    )
    return ControlledWorkerWindow.model_validate_json(json.dumps(value))


def recheck_manifest(
    a: AcceptanceFixture, reader: ControlledWorkerWindow, reader_owner: str, new: Any
) -> ControlledWorkerWindow:
    from commerceops.domain.commerce_values import facts_hash
    from commerceops.infrastructure.feishu_outbox_recovery import sdk_window_hash

    with connect(a.fixture.config.database) as db:
        sdk = db.execute(
            "SELECT * FROM business.p4_sdk_windows WHERE id=%s", (reader.window_id,)
        ).fetchone()
        claim = db.execute(
            "SELECT after_state FROM business.audit_events WHERE id=%s", (reader.window_id,)
        ).fetchone()
        gw_claim = db.execute(
            "SELECT after_state FROM business.audit_events WHERE id=%s", (reader.gateway_window_id,)
        ).fetchone()
        gw_end = db.execute(
            "SELECT id FROM business.audit_events WHERE source='feishu_gateway' "
            "AND action='termination_confirmed' AND entity_id=%s",
            (str(reader.gateway_window_id),),
        ).fetchone()
        worker_end = db.execute(
            "SELECT id FROM business.audit_events WHERE source='worker' "
            "AND action='termination_confirmed' AND entity_id=%s",
            (reader_owner,),
        ).fetchone()
    require(all((sdk, claim, gw_claim, gw_end, worker_end)), "P4A_READER_REQUIRED")
    assert sdk and claim and gw_claim and gw_end and worker_end
    value = reader.model_dump(mode="json")
    value.update(
        window_id=str(uuid4()),
        gateway_window_id=str(new.window_id),
        expires_at=new.expires_at.isoformat(),
    )
    value["recovery"].update(
        worker_window_id=value["window_id"],
        gateway_window_id=value["gateway_window_id"],
        expires_at=value["expires_at"],
    )
    value["recovery"]["explicit_ro_recheck"] = dict(
        recheck_count=1,
        reader_window_id=str(reader.window_id),
        reader_window_hash=sdk_window_hash(sdk),
        reader_claim_hash=facts_hash(claim["after_state"]),
        reader_owner=reader_owner,
        reader_termination_id=str(worker_end["id"]),
        reader_gateway={
            "gateway_id": str(reader.gateway_window_id),
            "gateway_hash": facts_hash(gw_claim["after_state"]),
            "termination_id": str(gw_end["id"]),
        },
    )
    return ControlledWorkerWindow.model_validate_json(json.dumps(value))


def native_negative_matrix(
    owner: DatabaseSettings,
    app: DatabaseSettings,
    directory: Path,
    deadline: Deadline,
    manifest_ref: Mapping[str, str],
) -> dict[str, Any]:
    """顺序单Worker、多份新fixture的原生准入与wire矩阵；仅HTTP transport为Fake。"""
    cases = (
        "numeric_string",
        "nullable_omitted",
        "missing_required",
        "duplicate",
        "wrong_content",
        "pagination_cycle",
        "timeout",
        "bool_number",
        "float_number",
        "revoked",
    )
    prepared: list[tuple[str, AcceptanceFixture, tuple[Any, ...]]] = []
    fixtures: list[AcceptanceFixture] = []
    records: list[dict[str, Any]] = []

    def sdk_count(a: AcceptanceFixture, window: ControlledWorkerWindow) -> int:
        with connect(app) as db:
            row = db.execute(
                "SELECT count(*) AS n FROM business.p4_sdk_calls WHERE window_id=%s",
                (window.window_id,),
            ).fetchone()
        require(row is not None, "P4A_MATRIX_LEDGER")
        assert row
        return int(row["n"])

    try:
        # 仅让原生30秒退避在准备其它fixture时自然经过；不并行Worker/改DB期限。
        for case in cases:
            private = directory / case
            private.mkdir(mode=0o700)
            a = AcceptanceFixture.prepare(
                owner,
                app,
                private,
                deadline,
                case_kind="batch_twenty_items",
                entry_manifest_ref=manifest_ref,
            )
            fixtures.append(a)
            prepared.append((case, a, completed_origin(a)))
        for index, (case, a, origin) in enumerate(prepared):
            old, original, worker_owner, delivery = origin
            a.wait_due(delivery["outbox_id"])
            gateway, gateway_child = a.gateway()
            try:
                if index == 0:
                    for fault in ("wrong_hash", "window_mix", "projection_hash"):
                        window = ordinary_manifest(
                            a, old, gateway, original, worker_owner, delivery
                        )
                        value = window.model_dump(mode="json")
                        if fault == "wrong_hash":
                            value["recovery"]["original_gateway_hash"] = "0" * 64
                        elif fault == "window_mix":
                            value["recovery"]["original_sdk_window_id"] = str(
                                prepared[1][2][1].window_id
                            )
                        else:
                            value["recovery"]["projections"][0]["projection_hash"] = "0" * 64
                        invalid = ControlledWorkerWindow.model_validate_json(json.dumps(value))
                        _, rejected = a.worker(invalid)
                        require(
                            rejected["exit_code"] == 1
                            and rejected["stages"]["AUTHORIZE"]["state"] == "FAILED"
                            and rejected["stages"]["PREFLIGHT"]["state"] == "NOT_RUN"
                            and sdk_count(a, invalid) == 0,
                            "P4A_MATRIX_ADMISSION",
                        )
                        records.append(
                            dict(case=fault, actual_negative_CLI_exit=1, native_ledger_rows=0)
                        )
                    window = ordinary_manifest(a, old, gateway, original, worker_owner, delivery)
                    request = worker_request(
                        a.fixture.config, a.business, window, a.fixture.private, a.external
                    )
                    ref = request["private_refs"]["window"]
                    raw = json.loads(bound_bytes(Path(ref["path"]), private=True))
                    raw["enabled"] = "invalid-bool"
                    write_private(Path(ref["path"]), raw)
                    request["private_refs"]["window"] = reference(Path(ref["path"]))
                    child = a.start(request)
                    value = child.wait(timeout=min(30, deadline.remaining()))
                    a.confirm_worker(child, value, allow_no_start=True)
                    require(
                        value["exit_code"] == 1
                        and value["failure"]["category"] == "ValidationError"
                        and sdk_count(a, window) == 0
                        and child.lifecycle_not_started,
                        "P4A_MATRIX_DTO",
                    )
                    records.append(
                        dict(
                            case="DTO",
                            actual_negative_CLI_exit=1,
                            failure=value["failure"],
                            no_native_start=True,
                        )
                    )
                    denial = a.start(
                        dict(
                            contract=CONTRACT,
                            action="sql_denial",
                            app_database_ref=reference(a.fixture.private / "app-database.json"),
                            output_file=str(a.fixture.private / "sql-denial.json"),
                        )
                    )
                    denied = denial.wait(timeout=min(30, deadline.remaining()))
                    require(
                        denied["exit_code"] == 1 and denied["failure"]["sqlstate"] == "42501",
                        "P4A_MATRIX_SQL",
                    )
                    records.append(
                        dict(case="SQL", actual_negative_CLI_exit=1, failure=denied["failure"])
                    )
                window = ordinary_manifest(a, old, gateway, original, worker_owner, delivery)
                if case == "revoked":
                    # 本轮新fixture明确撤权；collector和准入始终使用actual app。
                    with connect(owner) as db:
                        db.execute(
                            "UPDATE business.principals SET enabled=false,"
                            "auth_version=auth_version+1 "
                            "WHERE id=%s AND organization_id=%s",
                            (a.fixture.actor.principal_id, a.fixture.actor.organization_id),
                        )
                a.external_behavior("normal" if case == "revoked" else case)
                positive = case in ("numeric_string", "nullable_omitted")
                _, result = a.worker(
                    window, stop_after_verified=delivery["outbox_id"] if positive else None
                )
                with connect(app) as db:
                    actual = db.execute(
                        "SELECT status,complete_unique_verified FROM business.p4_base_deliveries "
                        "WHERE outbox_id=%s",
                        (delivery["outbox_id"],),
                    ).fetchone()
                    links = db.execute(
                        "SELECT count(*) AS n FROM business.p4_base_links WHERE item_id=%s",
                        (delivery["item_id"],),
                    ).fetchone()
                require(actual is not None and links is not None, "P4A_MATRIX_ROWS")
                assert actual and links
                if positive:
                    require(
                        result["exit_code"] == 0
                        and actual["status"] == "verified"
                        and actual["complete_unique_verified"] is True
                        and links["n"] == 1,
                        "P4A_MATRIX_CANONICAL",
                    )
                else:
                    require(
                        result["exit_code"] == 1
                        and actual["status"] != "verified"
                        and actual["complete_unique_verified"] is False
                        and links["n"] == 0,
                        "P4A_MATRIX_UNSAFE_VERIFIED",
                    )
                    if case == "revoked":
                        require(sdk_count(a, window) == 0, "P4A_REVOKED_SDK_STARTED")
                records.append(
                    dict(
                        case=case,
                        actual_child_exit=result["exit_code"],
                        expected_positive=positive,
                        native_ledger_rows=sdk_count(a, window),
                        native_method_counts=result["pg_proof"].get("method_counts"),
                        fake_transport_calls=result["counts"]["fake_transport_calls"],
                        expected_rejection=not positive,
                    )
                )
            finally:
                a.stop_gateway(gateway, gateway_child)
        return dict(
            expected_rejections=sum(not r.get("expected_positive", False) for r in records),
            canonical_positive_cases=2,
            records=records,
            suite_PASS=False,
        )
    finally:
        clean = [a.cleanup() for a in fixtures]
        require(all(clean), "P4A_MATRIX_CLEANUP")


def terminal_update_manifest(
    a: AcceptanceFixture, verified: Mapping[str, Any], gateway: Any
) -> ControlledWorkerWindow:
    """只从本轮合成PG原生RO/T6推导独立terminal DTO；不插入delivery或授权账。"""
    from commerceops.application.feishu_business.worker_window import RECOVERY_CAPS
    from commerceops.domain.commerce_values import facts_hash
    from commerceops.infrastructure.feishu_base_delivery import item_snapshot
    from commerceops.infrastructure.feishu_outbox_recovery import sdk_window_hash

    prior = verified["window"]
    recovery = prior.recovery
    require(recovery is not None, "P4A_HISTORY_REQUIRED")
    assert recovery is not None
    item_id = recovery.projections[0].item_id
    owner = verified["verified"]["pg_proof"]["worker_owner"]
    with connect(a.fixture.config.database) as db:
        item = db.execute(
            "SELECT * FROM business.replenishment_items WHERE id=%s", (item_id,)
        ).fetchone()
        outbox = db.execute(
            "SELECT * FROM business.outbox WHERE aggregate_id=%s AND aggregate_version=2",
            (item_id,),
        ).fetchone()
        plan = db.execute(
            "SELECT content FROM business.replenishment_plans WHERE id=%s", (recovery.plan_id,)
        ).fetchone()
        sdk = db.execute(
            "SELECT * FROM business.p4_sdk_windows WHERE id=%s", (prior.window_id,)
        ).fetchone()
        gw = db.execute(
            "SELECT after_state FROM business.audit_events WHERE id=%s", (prior.gateway_window_id,)
        ).fetchone()
        gateway_end = db.execute(
            "SELECT id FROM business.audit_events WHERE source='feishu_gateway' "
            "AND action='termination_confirmed' AND entity_id=%s",
            (str(prior.gateway_window_id),),
        ).fetchone()
        worker_end = db.execute(
            "SELECT id FROM business.audit_events WHERE source='worker' "
            "AND action='termination_confirmed' AND entity_id=%s",
            (owner,),
        ).fetchone()
    require(all((item, outbox, plan, sdk, gw, gateway_end, worker_end)), "P4A_HISTORY_REQUIRED")
    assert item and outbox and plan and sdk and gw and gateway_end and worker_end
    wid = uuid4()
    return ControlledWorkerWindow.model_validate_json(
        json.dumps(
            dict(
                schema_version="p4-worker-v1",
                window_id=str(wid),
                gateway_window_id=str(gateway.window_id),
                organization_id=str(a.business.organization_id),
                shop_id=str(a.business.shop_id),
                task_ids=[str(recovery.task_id)],
                expires_at=gateway.expires_at.isoformat(),
                enabled=True,
                profile="terminal_update",
                caps=dict(RECOVERY_CAPS),
                terminal_update=dict(
                    schema_version="p4-terminal-update-v1",
                    worker_window_id=str(wid),
                    gateway_window_id=str(gateway.window_id),
                    expires_at=gateway.expires_at.isoformat(),
                    verified_recovery=recovery.model_dump(mode="json"),
                    verified_sdk_window_hash=sdk_window_hash(sdk),
                    verified_gateway_hash=facts_hash(gw["after_state"]),
                    verified_gateway_termination_id=str(gateway_end["id"]),
                    verified_worker_owner=owner,
                    verified_worker_termination_id=str(worker_end["id"]),
                    external_id=verified["links"][0]["external_id"],
                    projection=dict(
                        outbox_id=str(outbox["id"]),
                        item_id=str(item_id),
                        client_token=str(outbox["provider_idempotency_key"]),
                        version=2,
                        projection_hash=facts_hash(
                            item_snapshot(item, plan["content"], 2).model_dump(mode="json")
                        ),
                        request_hash=outbox["request_hash"],
                    ),
                    request_key=str(item["resolution_request_key"]),
                    semantic_hash=item["resolution_payload_hash"],
                    resolution_id=str(item["resolution_id"]),
                    resolver_id=str(item["resolved_by"]),
                    resolver_identity_id=str(item["resolved_identity_id"]),
                    resolver_auth_version=item["resolved_auth_version"],
                ),
            )
        )
    )
