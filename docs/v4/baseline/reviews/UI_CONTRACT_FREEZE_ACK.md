# UI 合同冻结确认

结论：**ACCEPT_CANDIDATE**。对照 `evidence/CONTRACT_REVIEW_CANDIDATE_HASHES.json`，八个文件的当前 SHA-256 均与清单一致；该结论只绑定这八个哈希，任何后续修改需重新审查。本次增量未发现剩余 UI 合同阻断。

- 首审后余留三项 P2 已对照修订：UI 将完整 context 比较限定于敏感成功响应并区分匿名、控制回执与错误；permission 将无 Origin 403 明确限定写请求并引用 GET 例外；OpenAPI 八个 operation 均有 `x-cookie-purpose`。
- `SessionData.shops` 静态定义 0–2，说明 admin 不因双店种子默认获得业务 grant。permission 明确 V4 公开 bearer 不得被旧 `/api/v1` 接受，以及 persona/reset 原子撤销旧 bound session、logout/到期/撤权拒绝旧身份；旧权限桥接仍须专项 SQL/锁/ACL 审查。
- 本次没有重审全量合同，也未运行测试、服务或浏览器；哈希匹配及候选接受不代签实现、真实安全验证、阶段验收或 B 开发授权。

精确冻结内容以上述清单为准，首审和复审报告保留。
