# V41 完整增量合同独立审查

日期：2026-11-04（台北）。精确 source `84db1ba34120cac3b4fccb6bbe316d3efbca1659`，tree `a938c6cec22b347370e477c6044cd7835560b341`。审查对象为该提交 `docs/v4/v4-1/CONTRACTS.md` 全部七节，并结合此前已读的 API_PLAN 精确提交 6505e9d 和 V40 冻结实现；不读取作者 WIP。

结论：ACCEPT_FOR_SQL_CANDIDATE_WITH_TWO_IMPORT_P2。无合同层面 P1。允许 DTO/KPI、Shell、SQL 候选编写；以下 P2 阻断相关导入能力最终核收，不阻断其他独立切片。此结论不签真实 SQL/ACL/运行安全通过。

## P2-C01：解析槽位失联可提前释放

第6节规定 PG advisory slot 全局2/tenant1、解析退出/reap后释放。父进程异常退出或持锁连接断开会使 PG 自动释放 session lock，但独立解析子进程可能继续运行；新请求再次取得槽位时会突破实际并发上限。正常 finally/kill-wait 路径不能覆盖此情况。

最小修复：合同明确父进程和持锁连接失效后的解析终止、reap及重新准入协调；作者选可验证的最小方案，并证明没有活解析与重新发放槽位的重叠。故障证据需包含父进程异常退出、连接丢失、超时强停和随后再次准入，不能将 async/线程取消记为进程停止。

## P2-C02：preview 与确认的数据版本绑定不完整

第6节只明确 confirm 的预期 revision，没有规定 preview 保存创建时 data_revision、parser/schema version，也没有规定确认时同时匹配 preview、请求和当前数据版本。只将请求值与当前版本比较，会允许用新 revision 确认旧预览。

最小修复：保存以上版本及文件/映射/normalized摘要；新效果必须三方一致，数据变更需重新预览。不能仅替换请求 expected revision。原 key 已提交回执仍按当前身份/权限先核、回执重放先于新效果 CAS 的顺序处理。

## 全七节核查结论

1. 已有/新增：完整六卡和本地能力范围明确，未扩旧控制操作或 Worker；外部真实调用不在实现许可内。
2. 权限/事务：六表职责可接受，复合归属、窄 apply function、当前权限优先、业务回执重放与新效果 CAS 顺序正确。SECURITY DEFINER 可信身份输入、低权直调拒绝、effect/receipt/event约束、撤权与 reset 锁序仍待精确 SQL 核收。0024/25 allowlist、owner/环境校验保留及按tenant子表GC方向可接受。
3. KPI/版本：有效视图、tenant锁下读取、业务版本独立于身份代次、Decimal/币种/时间窗、未知支付和成本、退款事件与到账语义区分正确。金标仍需冻结缺时记录的可能影响区间规则。
4. HTTP/来源：新router需完整guard，JSON导出带context/revision、静态路由优先、混合来源显式表达与无模型容器可接受；精确DTO不得退回原始CSV响应或将混合来源伪装单一fixture。
5. 演示写：标签窄字段和单向demo履约、known paid_at前提、无库存/付款外部效果合理；履约效果需SQL证明。
6. 导入：预览不可变链、原子supersede、confirmed终态、每链/tenant/active-head配额、原键恢复和整批确认设计可行；需关闭上述两项P2。持久配额不代替解析并发。并发同parent子版本应仅一有效继任；归属/额度/epoch必须真实SQL核验。
7. 切片/Gate：单owner、精确SQL先审后运行、动态完整PG与全阶段六卡证据边界明确；旧V40结果不代签V41。

验证方式：只读合同与已提交源码、范围对照；未运行业务测试、SQL、服务或网络。后续提交必须另列审查来源。V40原失败与编排wrapper非零保留，不回填。
