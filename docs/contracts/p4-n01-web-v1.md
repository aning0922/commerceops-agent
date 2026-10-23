# P4 N01 Web 自然语言 preflight v1

2026-10-12（Asia/Shanghai）。A09 接口冻结合同；当前 DTO/端点已实现候选，实际测试/源码冻结独审/精确 CI pending。A 唯一后端 owner，C 按本合同接 M02。依据 Root 已授权接单：Issue42#6111983828、Issue40 A09 回执；不覆盖现有 CreateNewCycle/权限/幂等合同。严格导出见 [N01 OpenAPI](p4-n01-openapi.json)，独立资产并入运行时；原 P3 22 操作合同字节保留，本入口新增第23操作。

## 接口与准入

新增 `POST /api/v1/tasks/preflight`，Cookie session、精确允许 Origin、`X-CSRF-Token`、application/json、no-store/Vary 与现有 P3 相同。先当前 session/当前 operator 能力，再严格输入，随后在同一只读业务事务重新锁验当前 session/operator/shop。无能力 403 ACCESS_DENIED；目标 shop 不存在/非授权/跨组织/非 Mock-test 或来源元数据不匹配统一 404 RESOURCE_NOT_FOUND；会话过期/撤权 auth_version 变化 401 SESSION_INVALID；CSRF/Origin 403；非法 JSON400/严格 DTO422/类型415/服务不可用503，复用 p3-web-v1 error envelope，不回显原句或秘密。

输入对象 additionalProperties=false：`schema_version="p3-web-v1"`、`shop_id` UUID、`fixture_case` 1–100 字符（既有 inventory-v1 目录真实允许的 case，不能路径/URL）、`text` 1–2000 字符。无 actor/role/context_task_id/request_key/draft_token；fixture_case 是用户选中的 Mock 来源，不由自然语言猜测。

响应 HTTP200 外层继续 `schema_version=p3-web-v1, identity_mode=session, server_time, trace_id`；新增 `preflight` 严格对象：

| 字段 | 精确语义 |
|---|---|
| schema_version | `p4-n01-web-v1` |
| status | `ready / clarify / unsupported` |
| reason | `EXPLICIT_PARAMETERS / MISSING_PARAMETERS / INVALID_PARAMETERS / UNSUPPORTED_TEXT` |
| shop_id | 本次当前授权的目标 shop |
| source | source_mode=`mock`、dataset_version=`inventory-v1`、fixture_case、evidence_mode=`not_used` |
| window | kind=`last_seven_complete_days`、start/end（UTC，半开区间）、timezone、as_of（冻结 fixture clock）、source=`mock_fixture` |
| scope | kind=`all_fixture_products`、shop_id、source=`selected_shop` |
| candidates | L/R/S 三个对象：name、value 0–365 integer、source=`explicit_text / demo_assumption`、start/end；原句 Unicode code point 半开索引，仅 explicit_text 有整数索引，demo 为 null |
| missing | 缺少明确参数的 L/R/S 名称数组；非法/unsupported 不保留疑似明确参数 |
| draft | ready 时为现有 Parameters（source_mode/dataset_version/fixture_case/L/R/S），否则 null；不含请求键、批准事实或执行权限 |
| requires_confirmation | 恒 true |
| execution_available | 恒 false |

## 真实支持边界

确定性有限语法，不调用 LLM/provider，不宣称任意自然语言理解。支持原 PRD 请求 `分析最近七天的商品销量和库存情况，找出可能缺货的商品，生成补货建议。`、J01/M02 原句 `分析最近七天的销量和库存，找出缺货风险并生成补货建议`，以及 `分析库存`、`分析库存并生成补货建议`、`查看库存`、`查看库存并生成补货建议`、`生成补货建议`、`库存补货`，允许句首 `请` 或 `帮我`；意图后可选各一次 `最近七个完整自然日`（或 `最近7个完整自然日`）及 `全店`（或 `全部SKU`），两者顺序可互换，以 Unicode 空白/逗号分隔。只支持所选 Mock case 的完整产品范围和 fixture clock 下最近七个完整自然日；窗口/来源待用户明确确认，不冒已采集数据。指定 SKU/自定义日期/任务查询/解释及飞书关联续答均 unsupported；其原合同依赖仍 pending，不以本切片宣称 BC02/M1 整体验收或擅移 M2。

L/R/S 参数块复用已验收 P2 全消费文法：NAME 为大写 L/R/S，`=` 或 `:` 后 ASCII 无符号规范十进制 0–365（最多三位，无前导零；零写0），可选 `天`，Unicode 空白/中英文逗号/分号间隔及有限句末标点。重复、负数、bool/小数/分数/范围、超界、未知尾词或未完全消费 → clarify/INVALID_PARAMETERS；不截断、不猜参、不用尾缀黑名单。合法缺项 → clarify/MISSING_PARAMETERS；缺项候选显示 demo L3/R7/S2，不能成为 ready。非法/unsupported 三项候选全部回 demo、missing 全 L/R/S，draft=null。

例：`请分析库存并生成补货建议，全店，最近七个完整自然日 L=3天，R=7天，S=2天。` → ready；`分析库存 L=3` → clarify，缺 R/S；`分析库存 L=3 R=7 S=2 再退款` → clarify；`只分析 SKU-A 最近三天 L=3 R=7 S=2` → unsupported。返回窗口由服务端可信 fixture 元数据计算，与实际 submit 的 Mock 来源一致；不以服务端今日制造当前实仓窗口。

## M02 接线与零副作用

C 将结果用于本地草稿及明确结构化确认。文本/shop/fixture/参数/身份变化使旧响应和确认失效；异步旧响应不得覆盖当前草稿。仅 clarify/MISSING_PARAMETERS 可由用户明确补齐结构化缺项，再重新确认窗口/范围/来源与完整参数。clarify/INVALID_PARAMETERS 或 unsupported/UNSUPPORTED_TEXT 的原句不得以demo默认值、静默猜参或普通“确认”转成ready/可提交；须修正原句重新解析，或明确取消该原句、另开既有结构化新周期。ready 也不自动提交。B35 只本地确认，B01 才以全新键显式调用现有 `POST /api/v1/tasks` / CreateNewCycle；服务端仍重验当前 role/CSRF/request_scope，unknown 以原键核查，不换键盲建。

preflight 不创建/修改 task/job/approval/plan/execution/item/outbox/inbox/request receipt/业务 audit/CP、不运行 Graph/Worker、不持久化原句/通用 draft、不返回持久 capability。现有 session 活动时间维护属于认证记账，非业务写入。取消、歧义、非法、跨 shop/撤权/CSRF 均须实际 PG 零业务增量证据；现有创建、审批与恢复 Gate 分母保持。
