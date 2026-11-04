# V41 原子动作与guard候选专项审查

日期：2026-11-04（台北）。source `15ec5f4c77d2c05ad2ee224a5cb3274b312fb4b7`，tree `eadbaacc841f818328e02d78c5ef90e8a10093ff`。完整读取aab之后唯一0025增量及调用的既有actor/DDL/纯DTO；未执行迁移/PG，不读policy/锁序后续WIP。

结论：ACCEPT_REVOKED_ACTION_CANDIDATE / HOLD_RUNTIME_AUTHORITY。PUBLIC/app仍对全部新函数/表REVOKE，可继续候选实现；S01/S02在本SHA未修，不能授执行或签完整运行准入。新增P2-S03为SQL/Python标签规范差异，需在授权接线前对齐。

## 已核原子性结构

request_body固定operation/path/method/字段集合、UUID/数值词法及canonical/hash，不接受任意SQL对象。apply先current actor/CSRF/epoch/gen/权限，再查同owner/operation/key原receipt；同文原结果先于新revision CAS，异文拒绝。新tag核有效fixture/导入product及版本后仅更新覆盖；履约限定原模板且paid_at已知、首次单向状态；import核锁内job身份、STOPPED/READY/未supersede/未确认、时间、三方revision、parser/schema/job/normalized/mapping摘要、累计500、SKU/币种，再逐行写同事务。

effect/receipt/event均在同函数事务，receipt FK deferred；写后revision和effect summary绑定事件，末次权限/TTL复核保留。import原job-row来源与内容对应，ID服务端生成；不是外部库存/支付操作。payload结构与PythonTag/Fulfillment/ImportedProduct manifest静态对应，但SQL实际hash与原子回滚尚未运行。

mutation guard限制owner执行、禁止TRUNCATE、保留期及活解析容量保护DELETE；tag版本严格+1且换receipt，其余效果/历史不可UPDATE；preview限定可变生命周期字段，旧结果不可改写，STOPPED/UNKNOWN不倒退。deferred commit guard复核当前身份/expiry、回执身份与请求、类型对应效果、完整事件/effect count/digest和最终revision。只把代码结构视为候选，不把动态触发器执行、行锁或错误路径预签通过。

## P2-S03：SQL标签与Python规范不等价

v41_tags_valid使用btrim（默认ASCII空格）、POSIX控制类和NFC；Pythoncanonical_tags使用Python strip且原15ec未要求NFC，8707后还要求所有字符isprintable。例：不换行空格前缀在Python被拒绝，而SQL btrim不会移除、NFC不改变、该字符并非控制字符；反向的分解重音在Python被接受而SQL拒绝NFC不一致。新低权apply必须不能接受导致Python读取DTO拒绝的字符串，也不能让合法HTTP输入无说明地在SQL层改变语义。

最小修复：冻结一个跨层可执行的标签字符/空白/Unicode规范，Python和SQL一致拒绝或明确规范化；重点覆盖非ASCII空白、不可打印格式字符、NFC/NFD、普通中文emoji/公式样可打印文本。禁止只依赖前端trim或把SQL所有检查删掉。独立纯验证精确15ec的canonical_tags：NBSP前缀拒绝、分解重音接受；SQL分支为静态逻辑分析，尚未用PG复现，需实际跨层正反例确认。

## S01/S02及后续接缝

新apply依赖原v41_actor，commit guard亦没有当前policy版本来源；credential/identity检查仍未完整持行锁。Root已采纳owner-only singleton policy及稳定轮换顺序，是后续设计，不是本SHA实现。必须等新policy/current配置/同版本换secret拒绝/旧demo撤销及锁序专项；本审不自行改六表或预签第七表。

parse lease acquire/release、可信stop proof、preview slot持久fail-closed、preview落盘规范/额度、真实低权grant/store/router/GC尚待下片。commit guard允许preview_data仍NULL的job UPDATE跳过失效身份检查，是为过期后的lease清理；未来release必须以受信lease/进程终止证明限制，不能暴露任意job更新入口。

最终PG矩阵需覆盖缺receipt/event/effect、错digest、异文/跨shop/版本竞争、不同请求连续tag、同key重放、跨tenant、撤权/到期、preview篡改/旧revision/超限/一行失败全回滚、GC活解析保持等；同事务多动作导致最终revision变化的语义也应明确，不能假定多调用天然可批量提交。

本次只读SQL与两项纯DTO边界验证，无真实SQL编译/执行或权限实测。原S01/S02及历史失败保持，后续候选另按SHA审查。
