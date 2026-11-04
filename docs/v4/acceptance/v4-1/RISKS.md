# V4.1 范围、风险与证据限制

当前代码 `261f39904d8cd5a3d6ae070cdca4a7ae5cde4d6e` / tree
`34da95131e04d7360ea8aa5250ea40215bcb0713`；状态 **LOCAL_STAGE_GATE_ACCEPTED**。
235 Python/74 Node/Native40组件/TS/Mock33同源通过；Root转交r10两spec/consumer/SQL/closure实际完成，
Main最终独审4e4741ad已核收。AI工程视觉 `c7f508dc596878a327fbc8e175b4e9b369f538a6` 40图已核，
图像范围无P1/P2；这不是用户人工视觉审批，后者NOT_RUN。正式独审4e4741ad已转交，按261精确范围收口。

- **功能边界**：19阶段项只是合同内实现层级，不是原19个完整规划或99/99完成；80项未重评。
  14导航/12业务视图不等于规划全部66页。分类树未提供；库存未知不当0；规则建议不称AI或正式Task；
  异常订单当前仅支付时间未知筛选；时间线只用已知创建/支付/退款事件；不造物流或到账。
- **批量标签**：仅当前页去重IDs、完整替换/清空、逐项独立事务和串行CAS/原键读回；
  首错/UNKNOWN/取消停止，不跨页/全店，不保证整批原子。POST已COMMITTED但读回拒绝仍待核，
  不可清pending、误计rejected或自动续发。已有成功项不随后项失败回滚。
- **API计数权威校正**：公开ActionReceipt没有effect_count。consumer要求明确None，缺字段和
  伪造0/1/bool拒绝；None不代表数据库效果UNKNOWN。导入用严格真实readback.row_count及同job/file
  uploads核计数。逐原key的最终SQL receipt/event/once/effects/digest/canonical request仍是独立权威。
  原r9诊断是新consumer核旧材料副本，不把原parent1改0；详见
  [7b43权威独审](../../v4-1/reviews/MOBILE_EFFECT_AUTHORITY_7B43CBA.md)。
- **历史失败**：r8在首Native PNG前TimeoutError、原精确await未捕获；r9两spec通过但parent1，
  原错误码/stack未捕获，复制材料诊断有PNG几何不符，不回写成原现场错误。
  Mock r1/r2/r3与原route timeline UNKNOWN、先前测试漏洞/P2及修片均保留，不自动重放。
  新261 Mock33与r10不是旧案的改名成功。
- **视觉与设备**：40原图由AI逐图核hash/IHDR/view，32业务/3Shell/5Native；200%顶部只覆盖
  横向视口和当时页面区域，底部商品末行可读，不推导全部页面200%完整覆盖。390表格部分右侧列
  不在静态图内，需要横向滚动；图片不能证明图外内容、滚动发现性、touch或真机硬件。
  静态图不证明授权/键盘/交互，用户人工视觉审批NOT_RUN。
- **来源分账**：完整工程4601只属4fec；严格PG596+177并集773只属e7，保留预期unavailable native1；
  四HTTP只属54ab。261受影响检查、Mock及实际browser各按261原件，不标为新SHA Full4601/773重跑。
- **扫描**：261 canonical wrapper0，dir/index0；history native1、1760已审、0blocking分开保留。
  refs前后有变化，不称全refs冻结；新refs仍需按原规则审查，不扩例外。
- **工程证据限制**：4fec的after216安装字节、after identity/wrapper和停后ps仅有当时owner封存，
  无独立raw after map/ps文件。source双快照、三层native和注册组收口有原件，不能将布尔摘要
  升级为逐包/全机独立审计。PG容器内文件逐字节核验仍NOT_RUN。
- **资源关闭**：Root转交r10清理及独立closure=true，closedfinal摘要
  `0df4a06b87110816d449415bd5ad416b885de5d2f8191f10bf5781770462a192`；
  Main最终独审4e4741ad已核收。按案限定容器/网络/端口/进程/保卷，不推导全机无资产。
  HTTP/browser保卷与FullPG临时卷删除策略分开，不全局prune或删除旧卷补绿。
- **未验与未开始**：自然24h GC未验，历史GC为合成owned fixture；真实provider/模型/embedding、
  飞书/Woo业务外发、Hosted、production未验/NOT_RUN，V4-2 NOT_STARTED，实际模型费用UNKNOWN。
  公开依赖/安全审计访问不冒称全程零网络。

所有临时服务已关闭，**无持续可用URL**。仅能按 [复现入口](../../v4-1/proposals/LOCAL_DEMO_REPRODUCTION.md)
在Root新授权、精确source/工具/新owned资源和新UTC内重新建立演示；不提供死链接或声明产品发布。
本地运行与阶段收口已按4e4741ad核收；用户人工判断、外部与生产仍未核收。


本地阶段 **V41-01–06 已完成并核收**，仅限合成owned环境与原合同受控范围。最终runtime独审
`4e4741ad56e5ee8d3a22bc9f4ac6564715d92955` / tree `85f0293eb07d3d648949df47674d7965c6294f18`，
[正式原件审查](https://github.com/aning0922/commerceops-agent/blob/4e4741ad56e5ee8d3a22bc9f4ac6564715d92955/docs/v4/v4-1/reviews/FINAL_RUNTIME_R10.md)采用该文件后续“完整实际运行追加核收”段；早期build-only/pending原文保留其时点。
r10同261/imagee834：2spec、11keys（10mobile子集）、4preview、7receipt/event、26当前effects及
2个历史替换tag分记，最终SQL0；source/tools与唯一允许next-env生成差异已核。原API清理130、
execution summary NOT_WRITTEN、Native browser exit NOT_EXPOSED、human审批NOT_RUN不改写。
旧4fec Full/e7 FullPG/54ab HTTP继续只属各自SHA；阶段接受不等于99功能、66页面、真机触摸、
外部业务、Hosted或生产发布通过，V4-2 NOT_STARTED。
