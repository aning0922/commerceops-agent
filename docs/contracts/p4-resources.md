# P4 配置挂载与资源核实清单（无平台调用）

首批只使用[空配置](p4-config.example.json)及本Worktree全新PG。原P1 probe的env/secret存在、非空/0600/gitignored仅是Root元数据观察，不表示当前认证/权限/目标资源有效，也不授权A读取内容。旧六字段Base不能代替正式M1十五字段表。

## 本地结构核实

```bash
uv run python -m commerceops.entrypoints.feishu_business verify-config --config docs/contracts/p4-config.example.json
```

该命令只读明确选择的配置JSON，校验schema/组织店铺UUID/用户上限5/唯一群/绝对秘密挂载路径及sender=false。输出固定布尔与计数；不读取任何secret file、不构建SDK、不连接PG或网络、不读取.env。structure_valid不是platform_resources_verified。真实配置只存ignored私有0700目录/0600文件，禁止在日志/GitHub打印标识和连接信息。

## 审后受控只读诊断

Root另批目标、身份、cap、截止、原资源锁和停止规则后，才允许资源只读诊断。诊断须逐项留私有证据，公开仅分类/布尔/计数，失败停相关包；不得申请scope、建表或新增成员。

| 项目 | 必须核实的当前事实 | 首批状态 |
|---|---|---|
| 本地owner | 明确旧probe只读资源与全新P4 PG分离，身份文件归属/权限/无symlink | 旧资源内容未读 |
| app/tenant/bot | 当前自建测试应用、发布范围、bot真实open_id匹配 | not_run |
| A/B/C | 当前operator/approver/无权真实open_id→PGidentity→当前组织店铺roles | not_run |
| 唯一群/私聊 | 应用入群与@身份，群只允许原唯一目标，私聊目标受限 | not_run |
| 订阅 | 消息与新版card.action.trigger分别长连接配置，锁定SDK1.7.3 | SDK离线待证，平台not_run |
| Base目标 | 正式M1独立测试表15字段、类型/可空/读写资源授权，无生产数据 | not_run |
| Base权限 | create/update/read当前可用；scope与资源协作均需证明 | not_run |
| 原键/unknown | 旧P1原行/键/失败历史只读保留，不拿正式P4改写旧probe | 首批不读旧PG/Base |

若当前只有六字段旧表或缺十五字段表，报告blocked_external/具体缺项由Root裁决，不擅自建表或扩大授权。

## 后续挂载方案

P4 Gateway/单Worker使用同一新PG，运行角色commerceops_app；business config、nonce key、CSRF key、App Secret、Base app_token/table_id分别以read-only Docker secret文件挂载，参数仅传路径。不复制旧.env或secret到新库/工作区，不把真实标识写入Compose源码。Base别名m1-test由私有配置解析；B仅使用显式目标与SDK transport，A唯一协调器持有持久outbox和同表串行锁。

正式长连接和outbound受控启动命令待Root独审及有限窗口解锁；本批verify-config无live选项。Sender默认为false，旧P3/mock/controlled_stub禁发不升级。所有资源创建前登记owner/随机project/UID/绝对截止，停止仅自有容器/PID、保留卷/私有证据，不down-v/prune或处理未知资源。
