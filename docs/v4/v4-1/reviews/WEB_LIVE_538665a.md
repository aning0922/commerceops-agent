# 真实业务browser查询/分页P2修复独审

2026-11-04（台北）。结论：`P2_LIVE01_SOURCE_CLOSED / LIVE_BROWSER_NOT_RUN`，未发现本增量新的P1/P2。精确source `538665aebac7064c3d9b77bcbf65b4879b864123`，tree `151c5897ff4f1aa771a6b70750c38a015035a4ef`。对照 [830b97c原独审](WEB_LIVE_830b97c.md)，只读精确提交对象，不读WEB/QA WIP、不运行浏览器或服务；共享187接线由Main另审，不在本报告接受范围。

## 准确提交链

830b97c之后实际有五个提交，均仅改原两WEB路径：`44f818eb403b82fe16d0d0090b3c7287c35c4f78`跟踪/排空route和journal任务；`dad8f695de3cb60aa1e7144770d684d2634199d5`增加规则洞察可见断言；`f046d7ee33f0c5cb852c41c1d27b6303666f159f`将JSON解析失败替换为固定安全错误；`9b75490c1854837b30706b5e90e78067e5bfb816`强化查询结果；`538665a`增加CSV后实际分页。累计37新增/15删除，没有生产业务/schema/锁/配置变更。

## P2关闭依据

`waitProducts`现在精确匹配API origin、products路径、GET、shop、q与cursor。过滤改用已知SKU，要求total=1、next_cursor=null、结果ID精确为选择的商品；导入后搜索也要求total1/单项/无cursor，并核对应job、SKU、demo_upload及文件摘要。旧未筛选轮询无法匹配非空q；API忽略q返回原页也不能通过这些断言。

CSV导入成功后清空查询、获取首20项，要求total在21—40且存在原cursor，否则明确失败。下一页必须使用该cursor并具有同snapshot/revision/total、next_cursor=null，页间ID无交集且并集大小等于total；检查DOM已显示次页、首项消失。上一页等待空cursor的精确查询，回读ID顺序、原cursor、snapshot/revision/total与首屏一致，并核DOM返回；最后才记录pagination=OBSERVED。原缺cursor即NOT_AVAILABLE的可跳过路径已移除。

因此关闭原“忽略q仍通过/旧query可满足观察/未核回页就标分页”的源码P2。当前分页完整性是相对于服务端total的集合覆盖；虽然冻结正常源应为8+22=30项，测试没有逐一比较全部预期30个ID或22个导入SKU金标，不能把本片扩写为额外独立全量导入审计。实际浏览器完成仍须新case原件。

## 合成fixture规模与附带修复

新增CSV沿原一次discovery→mapping→confirm流程，数据为22个互异 `V41LIVE-CSV-00…21`，4列、983字节、TWD/非负整数金额、无公式/控制内容；XLSX保持原1437字节单商品样本。冻结种子每店8商品、10 SKU，纯解析验证两文件均READY且无质量问题，分别得到22和1商品；合计23导入SKU低于500，字段/单元格/文件和writer64KB上限有足够余量。四次preview/两次confirm的代码路径没有增加，不创建额外业务窗口；标签2/履约1也保持，计划仍为9个业务POST，非实际运行计数。

route任务加入flush等待，避免只等待已入writes集合；route.continue失败仅在仍有active记录时追加ACK_UNKNOWN，避免与requestfailed重复写。原intent等待writer成功后才发、原body/key、ACK/UNKNOWN、不自动重试不变。JSON解析异常使用固定错误不回显原始body；规则洞察新增的可见断言匹配当前生产界面。所有这些仍只是源码检查，没有以局部组件结果替代真实ACK/服务端提交。

## 独立验证与剩余边界

- 精确archive叠加已审95 writer接口、固定Node24.21与相同lock的只读依赖，`tsc --noEmit --incremental false` native0；未读187/WIP或声称共享集成已通过。
- 从精确spec提取原 `waitProducts` 函数，仅在本地假Response对象上验证正确查询及错误origin/path/shop/q/cursor/缺cursor/POST：8检查全部通过/native0，无浏览器或HTTP。该检查不覆盖真实网络调度。
- 直接执行冻结spec的CSV构造表达式得到983字节/22行；同SHA纯parser及ColumnMapping分别验证CSV22、XLSX1个normalized product均READY，无PG/资源。固定spec仍仅一个LIVE title。
- 首次本地提取尝试使用已安装TypeScript包的编译器API，因该版本未暴露ScriptTarget而失败；改为提取精确函数并用Node stripTypeScriptTypes后通过，实验性提示保留。没有修改候选代码或降低断言。私有验证产物在 `.audit/v4-1/browser-review-538665a/`。

作者的type/collect/preflight信息不替代实际browser；本轮未再次collect现共享配置。830报告中共享配置/subjects终态消费依赖由Main按新精确切片处理，本报告既不假定仍缺，也不代签已闭合。截图、原生200%、多尺寸真实业务和完整权限/阶段Gate仍按各自回执，不因P2源码关闭转绿。
