# P2-03：任务级库存分析持久化与只读合同

此切片承接已独审的 P2-01/02 `eb537e552456313100065551bc7f0b045fd08257`。范围是自有 Mock 数据的确定性分析、任务级观测快照、PG 报告、单 Worker/Graph 恢复，以及 BC01/05 的受控只读子集。原始 fixture/manifest/golden 字节保持不变；共享 `InventoryReport` 合同保持 P2-02 版本。模型、真实库存修改、采购、审批与执行均未在此切片调用。

## 1. 数据与权限

迁移普通增加 `0002_inventory_analysis`，保留 `0001_task_foundation`。新增 `principal_shop_scopes` 和五个只追加证据表：`commerce_snapshots`、`snapshot_products`、`snapshot_order_lines`、`snapshot_refunds`、`analysis_reports`。它们使用 organization/shop/task 复合外键；每任务只有一个逻辑快照/报告，逻辑键绑定 task 与 workflow version。快照绑定规范化请求内容及 SHA256；快照和报告均保留 canonical 内容与 SHA256，报告完整结构必须与 facts 一致。

金额列为 `numeric(20,6)`，应用发送 SQL 前校验精度和范围，数据库另将存储值与未舍入的 JSON 字符串比对，拒绝隐式舍入。库存/数量整数使用 `numeric`，不引入额外业务上限。未知库存、退款数量和在途信息保留原始 unknown/reason；分数采用精确分子/分母字符串，显示小数与 canonical facts 区分。

runtime 对授权表只有 SELECT，对证据表只有 SELECT/INSERT，没有 UPDATE/DELETE/TRUNCATE；owner 也受证据不可变 trigger 约束。既有 principal 不自动取得店铺 grant。固定参数、固定 search_path 的 `lock_inventory_permission` 仅锁定并验证当前授权，SECURITY DEFINER 不提供写权限；PUBLIC 的执行权限被撤销，runtime 单独授予 EXECUTE。这使 SELECT-only grant 可以在业务提交及读事务期间阻止权限变更竞态。既有 P1 表权限和 Worker 进程终止合同保持。

## 2. 采集与业务事务

采集完全在快照事务外执行。每端点最多 200 页，产品最多 1000、订单行及退款各最多 10000；同页可重试至多 3 次，每次等待至多 20 秒。稳定 ID 去重；缺页、容量、重复、持续失败均形成不完整解释。来源改变至多完整重采一次；第二次仍变化便保存不完整观测。采集时间、业务窗口、source provenance、完整性与 warnings 持久化。`consistency=observational` 明确表示观测快照，不推导平台原子一致性。

任务 kind 为 `inventory_analysis_only`，workflow 为 `p203-inventory-analysis-v1`。受控入口只接受自有 Mock fixture；参数 L/R/S 为显式 demo assumption。实际单 Worker 运行 PG checkpointer 的单节点 Graph；正常状态为 queued→analyzing→completed。快照、所有规范化子行、报告、任务完成及报告审计在同一业务事务提交，checkpoint 另行持久化。

completed 表示报告已经生成。不完整输入仍产生 `report_ready` 解释且报告 complete=false；只有完整、没有建议且没有待核事项才是 `no_action`。输入错误为 failed，权限或 checkpoint 不安全为 needs_attention；存储失败按既有 Worker 有界重试，第三次仍失败且 DB 可写时留 needs_attention。DB 不可用时不能伪称已写入终态。

恢复优先校验已有 PG 结果：必须同 task/org/shop、同逻辑键、请求绑定、snapshot/report hash 和完整报告结构一致。已提交结果的 job ACK 可以复用，不重复采集或写报告；这一确认不扩大 HTTP 读取权限。无业务报告的 analyzing/recover 任务如果缺少安全 checkpoint，不创建新 Graph。旧 workflow 仍由既有 Worker 拒绝。job.done 不自动变成 task.completed。启动时对已完成 analysis 任务的保护只认上述持久证据，不把 lease 过期当作旧进程终止证明。

## 3. BC01/05 只读子集

固定 OpenAPI 见 [p203-read-openapi.json](contracts/p203-read-openapi.json)。提供 GET `/tasks/{task_id}`、`/tasks/{task_id}/report`、`/tasks/{task_id}/events`，返回 `schema_version=p203-read-v1`、analysis_only=true、execution_available=false。

可信 test startup resolver 注入模拟身份，每次读取都从 PG 验证 identity、principal enabled/auth_version/operator 及同 organization/shop grant，并限制为本人创建的任务。operator+approver 不扩大范围；approver/admin 单独不能读。默认没有 resolver，匿名、客户端 principal/role/tenant headers 均不能产生权限。本切片没有正式登录/session/RBAC 管理界面。

| 情形 | HTTP / 固定语义 |
|---|---|
| 无可信身份 | 401 IDENTITY_REQUIRED |
| 当前身份/角色/授权失效 | 403 IDENTITY_SCOPE_DENIED |
| 不存在或超出本人任务范围 | 相同 404 TASK_NOT_FOUND |
| 已授权任务尚无报告 | 409 REPORT_NOT_READY |
| 分页/请求无效 | 400，固定安全 code，不回显原输入 |
| 数据库不可用/存储内容不可解析 | 503 DATABASE_UNAVAILABLE，不输出 SQL/DSN |

事件仅投影 inventory analysis 的三个固定 action；details 白名单只包含有效 UUID、bool、固定 state/outcome/code。原始消息、未知审计字段及原始异常不输出。默认 50、最大 100 条，按 occurred_at/id keyset 排序；cursor 绑定 task/org/shop/principal/auth_version 与版本，长度至多 2048。cursor 无认证语义，仍逐次核当前身份及范围。

BC01/05 的其他阶段部分、BC02–04/06–07、正式 session、真实模型、审批/执行、outbox 仍待所属切片 Gate。P2-03 自检不替代冻结 SHA 的独立审查和精确 CI。

## 4. 实际证据与资源

自有隔离 Compose 项目使用锁定 PostgreSQL 17.11 镜像，无宿主机端口；先实际核对 0001 head，再开发验证 0002。每项 PG 测试另建 UUID 专用数据库并在 finally 仅删除该数据库。受控子进程在报告提交后、checkpoint/job ACK 前被父进程 SIGKILL 并 wait；未确认终止时启动失败，完成显式 OS 终止确认后重启，只复用同一 snapshot/report/hash，数量仍为 1/1。

本地完整检查已通过676 offline，全量PG132项通过；最终游标/安全投影修正另作3项定向PG验证通过。自有容器/卷/网络、测试数据库残留均0。详细测试计数、检查、资源回收与冻结 SHA 以 [STATUS 新交接](STATUS.md#33-2026-10-10-p2-0102内部门禁与p2-03交付) 及同一 [Draft PR30](https://github.com/aning0922/commerceops-agent/pull/30) 的实际回执为准。测试使用 source=mock、identity=simulated、model=not_used、approval=not_used；不外推为真实平台、自然网络故障或长期幂等证据。
