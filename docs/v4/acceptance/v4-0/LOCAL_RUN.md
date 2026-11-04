# V4-0 本地 owned 运行与复现

本指南用于本机隔离测试：真实 API、PostgreSQL 与合成 seed，非真实商业数据、模型、embedding、邮件或飞书外发，也不是生产部署。每次使用新的 project、数据库、私有目录、凭据、端口、子网和 UTC 窗口；不复用历史 case、卷或凭据。执行前确认本机 Docker、Python/Node 锁定工具链、浏览器依赖、磁盘及窗口容量。示例中的 `<...>` 均需替换；不要将私有文件、配置内容或凭据放入 Git、终端日志或截图。

自动入口和历史回执是不同事实。可参考 `HTTP_LIFECYCLE_F1.json`、`TTL_F1.json`、`tests/e2e/v4/OWNED_DRIVER.md` 及实际回执中的 source、退出码、清理和限制；后续源码变化不自动继承旧结果。F1 的 legacy Web 7/10/7 与独立 N01 六项属于各自实际窗口；daily/inquiry/copy 三条独立浏览器操作流程不能由它们替代。Hosted、真实 provider 及生产结果不由本指南证明。

## 1. 当前源码和镜像

在 Root 已核定的独立干净 checkout 中操作。不要预填未来最终 SHA：

```sh
git rev-parse HEAD 'HEAD^{tree}'
git status --short
shasum -a 256 backend/migrations/versions/0024_v4_demo_foundation.py
uv sync --frozen --offline
PATH="$PWD/.tools/node/bin:$PATH" npm --prefix frontend run check:toolchain
```

Node 和 npm 版本以 `frontend/package.json` 的 engines 为准；需已有锁定依赖和本地测试镜像。固定 PG image 必须与本次源码和六个构建输入绑定，且实际 `docker image inspect` 的 ID 与绑定一致。对本次新树、新 0600 binding，用 `scripts.m3_pgvector.validate_binding` 核 source/tree 和 `source_hashes`，再用 `prepared_image` 核实际 tag、ID、架构和元数据；不得盲拷其他源码的回执。driver 的 manifest 还需本地 PG 和 test 两个 `sha256:` image ID，execute 会分别 inspect，缺失即停，不自动 build/pull。

以下命令仅在 Root 已给出**同一 source/tree** 的可信公开 binding 路径时使用，目标是当前新树中尚不存在的回执；不会构建或改 tag。预先用只读信息确认输入回执属于本批、普通文件、当前用户所有且权限 0600；不要指向旧私配。

```sh
export V4_APPROVED_BINDING="<absolute_current_source_binding_path>"
.venv/bin/python - <<'PY'
import json, os, stat
from pathlib import Path
from scripts.m3_pgvector import inspect_image, prepared_image, validate_binding
root = Path.cwd()
source = Path(os.environ['V4_APPROVED_BINDING'])
info = source.lstat()
if source.parent.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
    raise ValueError('binding source refused')
binding = json.loads(source.read_text())
validate_binding(root, binding)
actual = inspect_image(5)
if any(binding[key] != value for key, value in actual.items()):
    raise ValueError('actual image differs')
audit = root / '.audit'
audit.mkdir(mode=0o700, exist_ok=True)
if audit.is_symlink():
    raise ValueError('audit symlink refused')
fd = os.open(audit / 'm3-pgvector-image.safe.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
with os.fdopen(fd, 'w') as out:
    os.fchmod(out.fileno(), 0o600)
    json.dump(binding, out, sort_keys=True)
    out.write('\n')
    out.flush()
    os.fsync(out.fileno())
if prepared_image(root, 5) != binding:
    raise ValueError('new binding refused')
print('same-source image binding verified')
PY
```

当前共享 F1 PG 镜像与保护 alias 正在使用：不要重新 prepare、build 或 retag。冷机或不匹配时，先在独立授权窗口按 `docs/M3_LOCAL_DELIVERY.md` 和 `scripts/m3_pgvector.py` 的实际准备合同建镜像，重新绑定精确源码和输入；本指南不把旧镜像当成未来源码的证明。

## 2. 新 case 清单及自动验证

登记当前 UID、新 project、空库名、两个空闲 loopback 端口、两个互不重叠且与当前所有 Docker 网络 IPAM 不重叠的 canonical RFC1918 `/24`。示例 project 和数据库需分别符合 `v4qa_`、`v4_demo_` 规则。`starts_at`/`deadline` 写本次 UTC；普通场景不超过 1800 秒，预留至少 180 秒清理；`natural_ttl` 另有最长 2700 秒及自然到期要求。每个场景使用新 case，不复用 `execution.once`。

在新建的私有 0700 输入目录中，以 0600 文件写入以下结构；`directory` 是**尚不存在**、父目录已存在的 canonical 绝对路径。source/tree、迁移摘要取上面当前命令的实际值，UID 取 `id -u`。路径不含空格或 Compose env 特殊字符。此清单仅含资源标识，不填密码。

```json
{
  "project": "v4qa_<new_lowercase_id>",
  "database": "v4_demo_<new_lowercase_id>",
  "directory": "/absolute/new/private/case",
  "source_sha": "<current_git_head>",
  "source_tree": "<current_git_tree>",
  "pg_image": "sha256:<verified_local_pg_image_id>",
  "test_image": "sha256:<verified_local_test_image_id>",
  "api_port": 18440,
  "web_port": 13440,
  "starts_at": "<window_start_utc>",
  "deadline": "<window_end_utc>",
  "scenario": "lifecycle",
  "migration_sha256": "<actual_migration_sha256>",
  "uid": 501,
  "pg_subnet": "<new_pg_canonical_rfc1918_24>",
  "host_subnet": "<new_api_canonical_rfc1918_24>"
}
```

端口和 UID 只是格式示例，不代表本机可用或当前用户。`browser_lifecycle` 是另一可选 scenario；它还要求 `browser_lifecycle.py` 对当前 HEAD 的固定文件绑定通过。查其他可选场景以 `owned_driver.py` 的 `SCENARIOS` 为准。输入目录和 case 目录应位于不影响 clean-source 检查的位置。

```sh
.venv/bin/python -m tests.e2e.v4.owned_driver prepare --case "<absolute_input_manifest>"
.venv/bin/python -m tests.e2e.v4.owned_driver execute \
  --case "<absolute_new_case_directory>/case.json" --root-opened-window
```

`prepare` 只创建新目录和随机 0600 配置，不启动服务；`execute` 需在实际已登记窗口运行，启动前复核源码、镜像、端口、IPAM、空 project 和截止。它以新 project 运行 PG、迁移、checkpointer、runtime grants、fixture 初始化/验证、真实 API 和 Web，再运行固定 scenario。正常结束会停止 writers、采集 PG 事实、down 本次 project 并保留卷。检查实际 JSON 状态、每步 native exit、scenario 与 cleanup；`SCENARIO_COMPLETED_PENDING_REVIEW` 仍需结合回执审查，失败和 UNKNOWN 不重试或改写。若父进程被强杀，finally 不保证运行，须由操作者在登记的绝对截止内按本次项目身份核对并清理。

## 3. 手动浏览窗口

**以下是源码核对过的分步操作，尚未作为手动端到端流程验证。** 自动 runner 在执行完测试后会停服务，因此不能把其完成回执当作仍可浏览的服务。手动查看须另登记新 case、当前窗口、project、端口、两个 CIDR、镜像与外层截止/清理责任人，并执行第 1、2 节的 `prepare`。不要对已执行或已失败的 case 接续操作。

先冻结本次无 build Compose 模型。设 `V4_CASE` 为新 case 绝对目录；以下代码调用同一 driver 的校验、实际 Docker IPAM 盘点和模型冻结逻辑，不启动服务，失败即停。它会在新目录独占创建模型和摘要。

```sh
export V4_CASE="<absolute_new_case_directory>"
.venv/bin/python - <<'PY'
import hashlib, json, os, subprocess
from pathlib import Path
from tests.e2e.v4.owned_driver import Case, compose, no_build_model, private, verify_existing_subnets, verify_images
from tests.e2e.v4.owned_adapter import compose_environment
from tests.e2e.v4.supervisor import Budget
from tests.e2e.v4.preflight import utc

case_dir = Path(os.environ['V4_CASE'])
case = Case(**json.loads((case_dir / 'case.json').read_text()))
case.validate()
budget = Budget.bind(utc(case.starts_at), utc(case.deadline))
command = compose(case)
records = []
verify_images(case, command[0], budget, records)
private(case_dir / 'subnet_inventory.safe.json', json.dumps(verify_existing_subnets(case, command[0], budget, records)))
for args in (['ps', '-aq'], ['network', 'ls', '-q'], ['volume', 'ls', '-q']):
    out = subprocess.check_output([command[0], *args, '--filter', f'label=com.docker.compose.project={case.project}'], env=compose_environment(), timeout=5)
    if out.strip():
        raise ValueError('project is not empty')
raw = subprocess.check_output([*command, '--profile', 'test', 'config', '--format', 'json'], env=compose_environment(), timeout=10)
model = json.dumps(no_build_model(json.loads(raw), case))
frozen = case_dir / 'no-build.compose.json'
private(frozen, model)
private(frozen.with_suffix('.sha256'), hashlib.sha256(frozen.read_bytes()).hexdigest())
PY
```

后续命令需在 **bash** 中运行；先将变量设置为清单中实际值，确认模型摘要未变化、端口空闲、当前仍在窗口内并为清理留足时间。Compose 模型已绑定新项目的镜像、端口、目录和两个网络；PG 不发布宿主端口。不要向进程继承旧 DB、provider 或业务环境。

```bash
set -euo pipefail
V4_PROJECT='<exact_new_project>'
V4_API_PORT='<registered_api_port>'
V4_WEB_PORT='<registered_web_port>'
V4_MIGRATION_SHA='<actual_migration_sha256>'
C=(docker compose --project-name "$V4_PROJECT" -f "$V4_CASE/no-build.compose.json")
"${C[@]}" up -d --wait --wait-timeout 60 --no-build --pull never postgres
OWNER=("${C[@]}" run --rm --no-deps --pull never pg-test python -m)
"${OWNER[@]}" tests.e2e.v4.migration_diagnostic --public-migration-sha256 "$V4_MIGRATION_SHA"
"${OWNER[@]}" commerceops.entrypoints.database setup-checkpointer
"${OWNER[@]}" commerceops.entrypoints.database grant-runtime
"${OWNER[@]}" scripts.v4_demo_seed init-fixture --directory /run/v4_owner/export
"${OWNER[@]}" scripts.v4_demo_seed grant-runtime
"${OWNER[@]}" scripts.v4_demo_seed verify-fixture
```

每条均须实际退出 0 才继续；seed 的数据库提交与文件发布不是整体原子操作，失败时保留现场、不自动重试。`owned_api` 是测试专用装配入口，固定使用 `/run/v4_api` 新 runtime 文件及非 owner 连接，非生产启动器。先启动 API 并核实其 `/health/live`，再启动 Web；核实实际 API 与 Web 监听 PID/端口和 readiness，不使用其他进程已有的监听替代；服务须在本次期限内持续受外层看护。

```bash
"${C[@]}" up --no-deps --exit-code-from v4-api --no-build --pull never v4-api &
V4_API_WRAPPER_PID=$!
# 等待并确认本次 API wrapper 存活和 /health/live 后才继续。
env -i PATH="$PWD/.tools/node/bin:/usr/bin:/bin" \
  COMMERCEOPS_API_ORIGIN="http://127.0.0.1:$V4_API_PORT" \
  COMMERCEOPS_WEB_TRANSPORT=local_http NEXT_TELEMETRY_DISABLED=1 \
  .tools/node/bin/node frontend/node_modules/next/dist/bin/next dev frontend \
  --hostname 127.0.0.1 --port "$V4_WEB_PORT" &
V4_WEB_PID=$!
```

在实际登记的 Web origin 下浏览 `/v4`、`/v4/demo`、`/v4/settings/demo`。这是新本地合成演示，会话由页面流程建立；不猜测邮箱、密码或外部凭据。手动访问不是自动测试通过证明，也不证明外部质量。

在截止前停止本次已登记 Web 进程和 API wrapper，核实真实退出；再停止本次 API 容器，确认没有遗留 owner one-off。若需最终 PG 事实，必须在所有 writers 停止后、PG 关闭前由同项目受限 observer 采集。核对 Compose 模型摘要、project 标签、工作目录及实际容器归属后，执行 `"${C[@]}" down --remove-orphans --timeout 5`；不加 `--volumes` 或 `--rmi`。独立核对该 project 容器和网络为零、登记的 PID/端口已关闭，并登记保留卷。失败、超时、清理不确定时保留现场和实际状态，不操作其他项目或清空 Docker 网络。
