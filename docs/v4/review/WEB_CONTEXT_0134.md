# WEB context guard 小范围独立增量审查

日期：2026-11-03（Asia/Taipei）。结论：**P2_REQUIRED_CHANGE：0 P1 / 1 P2**。仅审基础上下文渲染保护，不签完整UI、服务器权限或真实API/PG/Web通过。

## 精确范围

- 作者commit：`0134cb7f76bc1e3645458860a6a1a2d85f1cef1f`。
- tree：`2835ca19990106734510fcd48a8670853e40052a`。
- parent：`fa96764cf2b8e3ab9adbb579b764f600a7d17e60`。
- 变更仅 `frontend/lib/v4-context.mjs`（24行）及 `frontend/v4-tests/context.test.mjs`（24行、两项node:test）。全部从精确Git对象读取，未读WEB当前WIP，未checkout或合入作者提交。
- 本轮静态审查，未执行两项测试或任何工具链/服务；作者测试的实际pass/exit不由源码推定。Reviewer仅新增本报告。

## WCTX-01 [P2] 缺失身份字段会被当成匹配的上下文

**位置：** `frontend/lib/v4-context.mjs:9–11`（establish），`:18–21`（accepts），绑定上述commit。

establish只以shop_id为null判断可建立session context，没有检查用于身份/代际比较的五个字段是否存在且有效。accepts随后对这些字段做相等比较；双方缺失时undefined严格相等，导致没有身份归属的响应也能获准渲染。

静态可推导的具体调用（未执行）：

```js
const gate = createContextGate();
gate.establish({ shop_id: null });
gate.selectShop('shop');
const ticket = gate.begin();
gate.accepts(ticket, { shop_id: 'shop' }); // 当前逻辑为true
```

tenant_id、organization_id、principal_id、reset_epoch和auth_generation全部缺失，但每项比较均为undefined===undefined。类似地，双方错误类型/空值相等也可能通过。此处不是服务器提权结论；风险是渲染层无法兑现“只有经核身份上下文才建立/接受”的保护。当前新增模块没有证明所有调用者已严格验证的类型边界，注释“server-derived”本身不能构成校验。

**最小建议：** 在establish建立状态前校验所用身份/代际字段的完整性与类型（身份为有效非空标识，epoch/generation为安全非负整数，session shop为null）；accepts对response做对应有效性核验再比较。可复用未来唯一strict Context解析器，不必重复实现另一套授权。若作者选择要求调用者预先strict解析，应提供明确且可执行的调用边界/接线证据后再核收，不能只增加注释承诺。此报告不要求helper承担服务器权限判断。

补一个针对缺失/无效身份与代际字段的拒绝回归；保留当前有效context通过、invalidate/换店/旧序号拒绝。现测试第二项:18–23只覆盖非null的session shop，未覆盖上述缺字段情况。

## 已核正确的局部行为

在输入context有效且由可信current读取建立的前提下：

- invalidate/establish/selectShop均推进本地generation和sequence，使先前ticket失效。
- begin递增sequence，accepts只接受最新ticket；相同context的早发请求亦被丢弃。
- accepts同时核ticket快照、当前context与response五个身份/代际字段，并核响应shop、ticket shop和当前选择一致。
- context与ticket采用浅拷贝；本次比较字段均为标量，避免外部原始对象修改直接改变所存这些值。

两项测试分别表达最新请求与principal/epoch拒绝、invalidate，以及换店/错误session shop；只是静态读取到这些断言，不称测试已运行。

## 后续接线边界（非本小切片新增阻断）

该helper没有负责获取current、验证服务器DTO、bootstrap/最小receipt例外、BroadcastChannel/可见性/轮询或服务端权限；本次不要求独立小模块提前实现完整UI。后续必须保证迟到的GET current不能无条件establish旧身份，控制操作开始invalidate并清敏感内容，匿名/错误/最小回执走独立恢复路径；这类调用端屏障须在整体冻结UI审查，不从本helper存在推定通过。

单个gate的全局最新sequence会互相取消并发业务读取，调用者须明确每个渲染槽的gate归属或串行读取策略；当前只有小模块，没有具体错误调用者，因此不另报现有bug。

等待作者对WCTX-01普通修订commit后增量复审；保留本轮首结论。不替作者修改实现/测试，不释放PG/Web资源，不把该结论升级为整体授权/安全验收。
