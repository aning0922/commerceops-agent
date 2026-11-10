# V41 业务client/界面接线链独立审查

日期：2026-11-04（台北）。source `301da4f61beac25646ec2fc3ad3c7df3a14488dd`，tree `508542f9ed6a72843d421073275806c97146fc5a`。按已核c343516之后23文件累计增量审查：dashboard/catalog/detail、单派发写、export/action、Root窄释放devIndicators配置及import/preview恢复helpers。只读git对象，不读后续WIP。

结论：HOLD_WRITE_LIFECYCLE_P2；两项P2限于业务写/恢复与会话结束接缝。只读helper和已审Shell可继续独立验证，旧Shell路由P2不重开。导入与最新API schema尚未同步/未接UI，不能按完整导入链核收；不是本报告签业务运行通过。

## P2-W02：写入/恢复401/403没有一致的当前上下文判断

`demo.tsx:146`的businessWrite catch只按错误status就clear并广播，没有像读请求catch那样检查原ticket是否仍当前。用户切店或另一标签切换身份并使本页refresh后，旧写迟到401/403会清掉更新后的session/context，违反迟到失败不能破坏新上下文。

相反，recoverBusinessWrite最后的catch不检查错误类别，只写提示；原key查询或settleWrite详情回读遇到当前有效上下文的401/403时，不清屏、不广播。可继续保留其他已渲染敏感数据至后续轮询，违反收到当前拒绝后立即清屏要求。两条路径都应按失败对应的请求context/shop/generation及槽位票据处理，不能只依赖五秒轮询。

最小修复：捕获适用于具体写/lookup/readback的请求边界，当前401/403清屏并广播，已经失效的旧请求不修改新身份。原key/proof继续保留UNKNOWN，不能因清屏丢掉待核对记录。增加组件级交错测试：发写→切店/跨标签新身份→旧401，以及当前恢复lookup/readback403；纯helper成功断言不覆盖这两条catch控制流。

## P2-W03：业务pending使退出永久不可用

`demo.tsx:166`在persona/reset/logout共同入口以writeState不为空一律return，渲染同样禁用所有三控件。业务REJECTED/UNKNOWN都保留pending；撤权、TTL或另一标签reset后，原context无法再次满足finishV41Pending，UI又没有保留未知记录并结束当前会话的通路。重新建立新空间也不会清除旧pending，继续无法主动logout。

最小修复：业务pending继续阻止重复业务写，但必须允许明确退出当前会话并保留原业务未知记录，不能以“清pending后再退出”伪造操作已解决。reset/persona如选择继续限制，应提供明确原因与安全结束路径；REJECTED与未派发/UNKNOWN的处理也须按权威证据区分，不自动换key。加pending后撤权/到期/跨标签reset、重新打开页面后仍可显式退出的组件测试。

## schema与实现范围：明确未完成，不伪签

已提交frontend v41-schema.json与b72331f的json_schema精确相等；最新eb73父链的ImportJobRef新增data_revision/parser_version/import_schema_version，当前前端schema缺三字段且additionalProperties=false。v41-pending.mjs:57还有旧五字段精确集合校验。因此同步不能仅替换JSON，还需更新preview存储/校验/版本恢复及测试；在此之前与最新API的导入响应会拒绝，不能签联调。

ImportPending仍禁用选择文件；encodeImportFile/validMapping/validPreview/finishV41Preview仅为helpers，demo未调用导入POST/恢复/confirm。finishV41Pending只支持标签/履约，import_confirm没有资源回读结算。该状态诚实展示待接入，可以保留为准备，不能把e037/301两个helper提交称为完整导入UI闭环。日期选择、钻取、异常/待办、read-context Copilot等也尚未完成，完整V41六卡Gate继续pending。

## 已核可保留机制

- client按冻结路径白名单/strict Ajv验证请求和完整响应；请求cookie/no-store、有界AbortSignal，POST单次fetch且预先登记原key，无自动重试/换key。Origin/权限仍由服务端负责，helper声明不是授权证明。
- createV41Gate有身份/店铺总失效代次及每slot序列，读成功需context相同、shop一致及status OK。dashboard/catalog/detail普通读错误使用票据检查，401/403清屏；隐藏/断网/BC/轮询沿用V40生命周期，新增业务state在clear/refresh时失效。refresh每次使请求失效的实际交互时长仍待组件/浏览器验证。
- catalog/dashboard对source与DTO无法表达的完整性不变量加校验，详情核请求ID，上传对象须存在于DatasetSource；React按文本渲染，不使用不可信HTML。日期/币种/未知值显示仍需业务金标联合验证。
- 导出完整schema与当前ticket通过后，再核page/export的revision/snapshot/source及安全固定文件名，随后Blob下载且撤URL；切店/清屏后旧ticket不能触发下载。尚无实际CSV生成与下载联调证据，不签注入防护端到端通过。
- pending仅存操作/key/对象/版本/来源digest/context等恢复proof，不保存CSRF/cookie/raw file/请求body；存储不可用或损坏fail closed。原key清除要求当前operator、匹配回执与同revision详情；preview引用先保存再清原key，失败保留以便恢复。此机制不授予权限。

## 独立验证及限制

从301da4f git archive提取lib、v41纯测试及冻结路由清单，使用已安装前端依赖和固定Node执行八个test.mjs文件：22 tests全部PASS、0fail/skip/cancel、native0、323.854ms。fetch均为测试替身，没有真实网络；stripTypeScriptTypes实验提示保留。源码schema对b723相等及对最新JobRef三字段差异独立核实。

22项是路由/client/context/dashboard/catalog/export/import/pending纯helper验证，不包含React effects/catch、实际session、浏览器、SQL权限或完整导入流程，因此不消除上述P2。未启动PG/API/browser/外部网络。当前报告不包含后续作者SHA；修复后需精确增量复审。
