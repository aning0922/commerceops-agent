# V41 HTTP recipes与PG观察器准备候选审查

日期：2026-11-04（台北）。source `6b90491aaa4bfbc762754f01ff4cc3f4ceff66f6` / tree `6f24c9789ff37d9eb00d607b19c042512e2951b0`。读取五文件及直接复用Visitor/owner_run、数据库connect和迁移schema配置；不调用真实HTTP/PG/probe。

结论：HOLD_RECIPE_ALIGNMENT，以下四项P2需修后再开实际运行。不是因SQL/router尚待交付而拒绝，而是已有recipe与已审合同/fixture的确定性不一致。

## P2-R01：履约读取不存在的version字段

http_recipes.py:349取order[version]，b723已审Order DTO及schema只有fulfillment_version且禁止额外字段。合法订单响应必在构造履约请求时KeyError，不能完成catalog_orders。

最小修复：使用fulfillment_version并在读回核版本推进/状态、原keyreceipt一致；增加真实schema形状的纯recipe构造测试，不添加非合同version字段来迎合测试。

## P2-R02：跨租户负例错误使用共有fixture对象

401—413行从当前products取第一个对象ID，另一Visitor在自己的默认授权shop查询该ID并期待404。fixture template UUID在各租户可相同，权限靠tenant/shop上下文；因此另一租户查询自己店铺的同模板商品可合法200。这不是越权，错误负例会阻断正确实现；若首项恰为导入对象，结果又依赖排序。

最小修复：明确用第一租户shop作为另一visitor请求目标，或第一租户独有导入对象并固定来源，期待404；同时核另一租户自己店铺同模板商品合法可读。不要按列表第一项猜隔离对象。

## P2-R03：响应context核验遗漏organization与目标shop

Business.call约184行只比较tenant/principal/epoch/generation，漏organization_id和shop_id。session context.shop_id本来为null，业务response应匹配实际请求shop，不能直接和session整个context相等。当前宽松分支会接受同tenant错误shop/organization响应，无法作为多店来源/权限验收依据。

最小修复：成功响应逐字段核完整身份元组，shop精确匹配本次有效请求目标；查询覆盖shop时亦用实际目标。拒绝缺context、错organization/shop及UNKNOWN冒成功，补strict Ajv能通过但跨上下文的反例。授权时间可变化，不以整对象字节相等代替正确字段比较。

## P2-R04：PG迁移版本表未限定schema

pg_observer.py:49查询无schema的alembic_version；backend/migrations/env.py明确version_table_schema为business，connect只使用连接参数，没有设置search_path；当前owner_run/配置接缝也没有为该查询设定business路径。默认search_path下会UndefinedTable，导致tenant观察及最终schema观察失败。

最小修复：明确business.alembic_version，保持只读事务/固定对象/参数化tenant。以最终新owned库验证真实0025和精确六表；不通过全局放宽search_path或改迁移位置绕过。

## 已核与后续范围

HTTP调用无重试/proxy/重定向继承；写前保存私有原key/payload状态，读取原preview/action COMMITTED后才显式重复同键十次，UNKNOWN不自动重发的方向可保留。导入CSV/XLSX为固定合成文件，预览不写商品、确认效果/receipt/event计数一次、SKU可查询与商品KPI同revision、错误行拒绝均为候选断言，未运行不能签通过。

Ajv读冻结合同、严格拒附加字段/类型漂移、输出固定安全结果；作者测试显式取b723，当前QA提交自身尚无最终API_CONTRACT/router，运行前需与Root最新schema对齐。新JobRef字段及真实状态码/回执形状不能靠旧8项validator纯测试代签。

PG observer固定表名、BEGIN READ ONLY、statement5s/lock1s、DB UTC、安全异常和无任意SQL接口方向合理。当前仅counts不足以证明所有行内容/once关系；最终事实与receipt关联、跨tenant未变、真实未知后恢复及故障回滚还需完整场景。shell_navigation尚明确拒绝，不能称已包含浏览器recipe。

pending.private文件保存原始上传payload，仅允许本次0700/0600私有证据目录；不可复制到public报告。成功后只是内存pending=None，磁盘仍保留ACK状态，不得称其已形成完成/恢复账本。最终规范回执应补原key最终核对状态而不删除原证据。

本次静态核查并从b723 JSON实核Order字段，不执行driver或recipe，没有Docker/PG/API/browser/network。作者35pass/8项Ajv等转交数字未作为Reviewer独立运行结果，旧失败保留。
