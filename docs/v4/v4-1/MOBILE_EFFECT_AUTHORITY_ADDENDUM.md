# V4-1 移动端效果证据字段权威校正

2026-11-04（台北）。Root 与专项独审确认：公开 ActionReceipt DTO 没有 effect_count，
原 producer 因而诚实记录 null。旧移动消费者与合成 fixture 错把数据库字段当成 API 字段，
导致 r9 移动独立纯诊断拒绝。r9 仍保持原 parent native1；不得改其原件或补签成功。

本窄批先由 GATES 冻结 Native CJS/TS 与原 Python pin，之后 Python 文件完整 owner
转交 QA，在 browser_shell.py/test_browser_shell.py 校正字段来源并同步最终 Native pin。
所有角色都只读取另一作者冻结 commit，不交叉写 WIP。实际最终链为 bb3775，
effect 逻辑冻结 7b43；Native 最终 C8 源码与两调用者三 pin 为 0023672b…396c538。

消费者要求 effect_count 字段明确存在且为 None，拒绝缺失、布尔和伪造数值。
提交状态、原 scope/key/CAS/version/revision/fresh readback/value 原条件保持。
导入使用真实 readback.row_count（严格整数 1—500），绑定 discovery/mapped/import 三段，
并核同 job/file_digest 的上传来源条目数；不把它伪称公开 API 的数据库效果计数。

数据库一次效果权威仍是未改的 final_facts.py：按原请求键、receipt/event/effect_count、
效果摘要、版本及原请求核验；原 owned_driver checked(final_facts) 失败会导致整案失败。
两者均未改。原 r9 SQL 实际通过，与 UI 字段为 null 是分层事实，不能写成 DB UNKNOWN。

新逻辑 235 项完整离线测试通过；校正消费者对 r9 冻结证据副本的单次只读诊断通过
32 PNG/11 keys，只证明新消费者与该原材料相容，不恢复原 registry/once 或改变旧案。
最终新源码必须再运行完整原业务/Shell/Native/父校验/SQL/清理，才可核收阶段。
真实外部业务、Hosted、生产与下一阶段仍不在本批范围。
