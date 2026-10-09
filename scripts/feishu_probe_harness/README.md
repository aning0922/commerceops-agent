# P1-05 受限技术探针公开交付核心

本目录交付真实联调使用的必要核心逻辑与合成复现，不包含私有环境、真实输入、平台标识、nonce、token、密钥、原始 payload、PG 行归档或历史运行 manifest。实际 G3 尚未完成。

这些核心来自已独审冻结的本地运行包。公开版只做相对 import、动态 SDK/JSON 边界类型标注、格式与必要集合标注适配；每个核心定义的规范化 AST 已与冻结原版核对一致。[运行原版与公开版映射](../../docs/P1_05_PUBLIC_SOURCE_MAP.json) 分别记录 whole-file SHA。公开适配版只做过离线回归，未用它连接真实飞书，不能用原版平台结果冒充公开版平台测试。

## 可复现的源与检查

| 模块 | 作用 |
|---|---|
| base_live_core.py / base_query.py | 固定 ProbeID/目标/持久键/六字段边界、页面与 method 上限、原 BaseProbe unknown 对账 |
| base_http_deadline.py | 独立无 WS 子进程的 list HTTP 等待值最多5秒，按每次剩余 normal deadline 夹紧并恢复公共边界 |
| base_closeout.py | 默认原记录 update一次及完整读回；默认关闭的当前匹配→原键第二create一次→完整读回→update排序；未知即停 |
| behavior_observer.py | 原 handler/receiver 一次委托、commit-return/DTO-ready/固定分类观察，失败不改 ACK，不声称 wire或客户端Toast |
| card_behaviors.py | C同回调同原事务资格见证、M3预期动作、原卡受限行锁；不改变身份角色 |
| card_readback.py | 既有四卡的纯字段、原actor/scope/anchor、value与语义hash、事件键关联核对 |

项目既有锁依赖不变，在仓库根运行：

```sh
uv sync --frozen
uv run --frozen --no-sync pytest tests/feishu_probe_harness -m offline -q
uv run --frozen --no-sync ruff check scripts/feishu_probe_harness tests/feishu_probe_harness
uv run --frozen --no-sync ruff format --check scripts/feishu_probe_harness tests/feishu_probe_harness
uv run --frozen --no-sync mypy scripts/feishu_probe_harness tests/feishu_probe_harness
```

测试使用合成 UUID、身份、payload 与官方 SDK 的真实公共 DTO/request 类型，fixture阻断 socket连接和子进程，不读本机真实配置，不需要飞书凭据或PG。范围包括固定键/字段、分页不全/重复/anchor不符、unknown停止、公共HTTP预算恢复、M3原DAL决定/重复/冲突、C纯合同与原拒绝同事务，以及观察器失败不能伪造成功ACK。

## 空配置与受控运行

[空配置](empty_config.example.json) 所有资源、身份与秘密路径均为空，execution/external_ready/replay全部false。它只说明必要配置形状，程序不会自动读取该文件或当前目录dotenv，不生成可直接执行的 live 命令。

真实运行由主控在专用任务环境使用原已审本地 dispatcher/manifest：只有明确当前窗口与范围授权后，原四锁、共享barrier、前消费者dead/reaped、专用PG/image/network、九身份映射和固定合同准入全部满足才启动。秘密仅0600文件只读挂载，目录0700，完整归档0600且ignored。公开核心不是独立实时运行入口，不替代这些控制。

Base默认scope最多update1/list2、create0；成功后原键第二create模式另需真实用户范围确认和主控新派发，原payload/键/anchor当前完整匹配后最多create1，只有明确API成功及完整唯一postcheck才接update，整包list最多4。未知即使查询恢复也不自动续写，不换键/删行/制造拒绝。两个scope的update次数还受原PG pending_kind在SDK前持久提交约束，pending update禁止再写。

原总parent30/normal24/cleanup27及watchdog不延长。HTTP等待参数不是整个请求墙钟硬时限，整体由原dispatcher/watchdog保证。SDK默认及callback关键路径的2秒/<3秒合同不改；Base不在callback关键路径。SDK私有连接/协议/ACK不修改。

实际 W1/M1/M2/Base 的证据与边界见 [联调快照](../../docs/P1_05_LIVE_DELIVERY.md)。卡片仅模拟技术决定，不创建补货工作项、采购、库存、退款、支付或真实订单副作用，不进入Phase2。未完成项保留not_run，Draft/CI/合并不自动表示G3通过。
