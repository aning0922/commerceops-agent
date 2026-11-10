# M3 本地日报演示启动单 v1

2026-11-03 后续窄修复候选：Root 授权对本 seed 增加真实连接 owner 前置核验。脚本在
mkdir/initialize_p3 之前，同一连接核 current_database 等于显式目标、current_user 等于
business.organizations 普通表的实际 owner；拒绝后不进入初始化器。原 namespace 与空库
限制继续适用。两个 seed 入口合计新增 12 项连接数据 double 反例/边界检查通过，
不作为实际 PG 或本启动单已执行证据；详见[询单准备单的 owner 修复记录](p6-inquiry-local-demo-v1.md)。

绑定Backend源码 `32dd7c240b9d2d979bf684eeb1dc8bcba7e35d31`；
Root组合树还须含实际0019/0020/0021父链。本文只给启动单，不表示命令已运行或SQL/UI已通过。
共享API/Worker/database源码保持该冻结；Root统一整合询单/K3后的启动参数以该组合实际入口为准。

## 1. Root填写的新owned对象

所有进程在同一个Root固定源码树、同UID和同文件路径视图执行；私配的路径是绝对路径。
PG镜像、资源名、具体UTC截止、API/UI监听端口及父进程native wait由Root统一登记。
本单沿当前代码默认使用API `127.0.0.1:8000`、UI `127.0.0.1:3410`，不混用localhost。

| 值 | 要求 |
|---|---|
| COMMERCEOPS_DB_HOST/PORT | 仅本次新owned PG的实际可达地址；宿主或容器地址与启动进程所在环境一致 |
| COMMERCEOPS_DB_NAME | `m3_daily_demo_` + 1–40位小写字母/数字/下划线，新空库 |
| COMMERCEOPS_DB_USER | 本次新owned表owner，供迁移、runtime grant和seed使用 |
| COMMERCEOPS_DB_PASSWORD_FILE | 新owner密码文件，绝对路径，不输出内容 |
| COMMERCEOPS_DB_RUNTIME_PASSWORD_FILE | 本次新runtime密码文件，供grant-runtime与种子生成runtime配置 |
| TASK_M3_DEMO_DIR | 不存在的绝对目录，父目录已存在；种子会创建0700目录和0600文件 |
| TASK_M3_ORG | 从seed输出demo.json读取organization_id，非秘密UUID |

Root先在实际组合源码执行migrate、setup-checkpointer、grant-runtime、revision核对；
用已固定的pgvector派生镜像。不要在缺0021父迁移的Backend单树直接升级0022。
seed要求business.organizations为0，非空会拒绝；失败保留新资源，不自动重试。

## 2. 种子与产物

在Root新owned窗口内，沿已经登记的COMMERCEOPS_DB_* owner连接执行：

```sh
uv run --frozen --offline python -m scripts.m3_daily_demo --directory "$TASK_M3_DEMO_DIR"
```

脚本不启动PG、API或Worker。它复用本地合成fixture构造器：生成新org/shop/principal/identity/
credential/session，并按DB UTC当前时刻的Asia/Taipei昨日生成订单、退款和manifest。
因此不是读取任何旧店、旧平台登录或已用Secret。生成的初始technical_fixture任务没有job，
正式日报任务由后续POST创建，验收计数应把技术种子行与日报行分开。

| 产物 | 用途 |
|---|---|
| configuration.json | WebConfig，内含runtime DB配置及csrf/nonce文件引用 |
| csrf-material、nonce-material | 新随机材料，仅私配读取，不输出内容 |
| daily-deployment.json | DailyDeployment，含登记binding；模型/实际sender关闭，schedule/Fake发送默认关闭 |
| daily/ | 新metadata、合成orders/refunds、manifest，均与本次binding/digest一致 |
| local-login.json | 新Web login/password，0600，交本次UI或HTTP测试读取；不打印到日志 |
| local-session | 种子TestClient已建立的session token，0600；不代表浏览器已登录 |
| demo.json | 非秘密org/shop/day/version和两配置路径，可用于填参数 |

API/Worker加载私配要求文件属主等于运行UID且权限0600；不要把同一路径换成另一容器UID读取，
也不要对未知挂载做chmod/chown。configuration.json中的DB地址/密码文件引用必须在实际启动环境可达。
演示账号默认operator+approver，没有admin；不会自动开启schedule管理或登记目的地。

## 3. API、唯一Worker与UI

Root按父窗口进程管理逐个启动并登记PID；以下是每个进程的前台命令，未包含后台shell或常驻启动器。
两个后端进程共用生成的配置：

```sh
export COMMERCEOPS_P3_CONFIG_FILE="$TASK_M3_DEMO_DIR/configuration.json"
export COMMERCEOPS_M3_DAILY_CONFIG_FILE="$TASK_M3_DEMO_DIR/daily-deployment.json"
export COMMERCEOPS_HOST=127.0.0.1
export COMMERCEOPS_PORT=8000
uv run --frozen --offline python -m commerceops.entrypoints.api
```

另一受控进程带相同两配置，唯一Worker：

```sh
export COMMERCEOPS_MODE=test
uv run --frozen --offline python -m commerceops.entrypoints.worker test-run --organization "$TASK_M3_ORG"
```

原Worker会取得同organization唯一锁并执行原termination gate；本单不授权强行绕过旧owner确认。
上述test-run在有DailyDeployment时注册日报与模板追问版本，沿原Composite单槽，不额外传旧库存fixture。

当前已提交前端使用这些公开环境变量；Root整合新增UI后按其实际消费核对：

```sh
export COMMERCEOPS_UI_MODE=live
export COMMERCEOPS_API_ORIGIN=http://127.0.0.1:8000
export COMMERCEOPS_WEB_TRANSPORT=local_http
npm --prefix frontend run dev -- --port 3410
```

Node/npm使用项目固定版本与Root已确认依赖，不在此单安装或更新锁。
浏览器入口为 `http://127.0.0.1:3410`。种子WebConfig.origins包含该Origin；
若Root选其他UI端口，必须在启动前针对本次新私配显式同步，不能把CORS/CSRF检查关闭。

## 4. 最小真实闭环与记录

1. 浏览器用local-login.json的新凭据登录，获取当前session/CSRF；local-session文件不能证明浏览器会话存在。
2. GET daily-capabilities指定demo.json的shop_id，核enabled/source/version/day范围和actual sender=false。
3. POST daily-reports携带p6-m3-web-v1、shop_id、source_config_version、全新UUID request_key和demo业务日。
4. 轮询返回的同task_id，核queued→analyzing→completed及report/snapshot/content/facts绑定，核受控Mock/模板标签。
5. 原键同正文重读受理回执，不新建第二任务；记录实际task/job/snapshot/report数。
6. POST四类之一的追问，携带同报告完整引用、p6-daily-question-v1和独立request_key；读原question_id缓存及引用。
7. GET evidence明确report_id，核最多50条、total_evidence_count/next_cursor及脱敏字段；GET不再采集或创建任务。
8. schedule/Fake实际恢复与unknown另按S3 PG矩阵，不因该日报UI闭环就签收投递Gate。

记录实际HTTP状态、任务/引用、native退出、是否清理和未跑项；不保存密码/token/raw平台body。
模型、embedding和真实消息发送始终关闭；Fake sent也不能改记实际平台推送成功。
Root父窗口先停止API/UI/Worker并native wait，核连接退出，再停新PG并保留新卷；
截止不足时停止并保留失败/UNKNOWN，不用同次剩余时间改称新窗口。

## 5. 本单作者验证

仅运行m3_daily_demo、daily_source、daily_schedule、worker四个CLI的 `--help`，均native0；
这些路径在argparse退出前不读取配置、不连接PG，也不启动服务。
启动环境变量、WebConfig.origins/UID/文件权限和CLI参数来自绑定源码静态核对。
seed、真实HTTP服务、Worker/UI闭环未由本owner运行；实际结果仍由Root新owned窗口回交。
