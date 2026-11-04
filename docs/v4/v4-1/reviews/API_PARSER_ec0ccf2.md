# V41 CSV/XLSX纯解析独立审查

日期：2026-11-04（台北）。source `ec0ccf2223d53ed0ddc2f71c139900d2d73bcacc`，tree `254f6d530637536bb0e223b7f5fac9f5d1a7b62a`。读取imports.py完整743行、test_imports.py及EMPTY_DATA DTO/schema增量；不读作者WIP。

结论：HOLD_XLSX_SEMANTICS_AND_ERROR_BOUNDARY，两项P2。并非因未接DB/子进程而拒绝：纯解析可独立交付，但当前真实字节反例会被错误接受或逃出固定异常边界。CSV及其他纯服务可继续独立开发。

## P2-I01：样式0与numeric类型未经语义核验

imports.py的metadata允许styles.xml和numFmt/xf节点，却不解析cellXfs实际样式含义；sheet约610行仅将缺省或s=0视作允许格式，且kind=n的值没有十进制词法校验。Excel样式索引0也可以指向日期/自定义格式，不能按索引数字推断General。numeric声明也不能直接当字符串读取。

精确源码纯复现：git archive导出该提交backend/src和原测试fixture到临时目录，用locked Python加载原parse_file/quality_preview。以原真实OOXML fixture增加styles关系，cellXfs索引0的numFmtId=14；C2改为s=0、numeric值45200。结果READY、商品price为45200，违反拒绝日期/复杂格式的合同。第二反例将A2改为numeric类型而值为非数字SKU，结果仍READY。未用parser mock。

最小修复：校验样式表结构及有效格式，明确只接受的General/普通十进制子集；日期/百分比/自定义复杂格式及未知style引用拒绝，包括style0。numeric单元格先严格校验有界十进制词法，再走字段映射；不能将非法numeric当文本。若不支持样式解析，可对含非支持样式的工作簿明确fail closed。补真实style0日期/百分比或自定义格式、非数字numeric、正常数字和inline/shared-string回归。不能仅补拒绝s非0用例。

## P2-I02：损坏DEFLATE逃出固定安全异常

_archive约374行调用ZipExtFile.read，约381行异常列表未覆盖zlib.error。把原合法DEFLATED工作簿的worksheet压缩数据首字节改为非法块（保留目录/容器结构）后，parse_file实际抛zlib.error，而非FileRejected固定原因。服务若只处理FileRejected将变成未预期内部错误，质量拒绝路径不完整；尚未有router，不能声称已经发生公开泄漏。

最小修复：在压缩读取边界明确捕获解压格式异常并转固定安全FileRejected/from None；不要将预算/资源异常悄悄当成功，也不回显原文件或原始解压异常。补损坏DEFLATE、CRC/截断和正常压缩文件真实字节用例，验证安全错误类型/原因且无部分normalized商品。

## 已核可保留机制

- 原文件2MiB及canonical base64上限，ZIP EOCD先限32entry/central directory大小，再建ZipFile；精确part白名单、重复/加密/symlink/未知压缩拒绝；声明膨胀比及实际解压累计8MiB/单part2MiB逐块检查，不extract或访问网络。
- XML 4096字节增量feed前跨块检查声明危险标记/NUL，PI拒绝；深度16、累计节点60000、属性个数/长度与文本限额，worksheet namespace/父子结构/单sheetData、连续row及A-X列索引有约束。shared strings有数量/单cell限制。已有字节上限控制解析树规模，不能据此称已证明硬内存上限或两秒杀进程。
- CSV限UTF8/BOM、严格reader、行列/单cell边界，表头strip/NFC后唯一；公式样单元格在质量阶段拒绝且sample替换为安全标记。映射不齐/宽度不齐/重复SKU/币种/价格/标签问题令products整体为空，错误100/sample20有界，已知小计不冒充部分导入成功。
- SKU ASCII casefold、title/tag NFC、Decimal规范化、完整文件digest与不含base64明文的请求摘要方向正确。当前纯函数输入ParsedTable应仅来自已审parse_file，不能未来直接用客户端构造表绕过文件上限。

## 验证与后续Gate

本次独立执行三项内存字节反例（style0日期、非法numeric、损坏DEFLATE）；临时源来自精确git对象，无DB/网络/服务/业务数据写入。作者累计61pure仅为转交报告，本次未重跑完整作者suite，不以其数量消除上述反例。

ParseBudget只在处理块/事件/行间协作检查：decode、单次csv解析、解压/词法调用及quality_preview并非可抢占硬deadline。两秒终止/reap、父/连接失联槽位保留、真实HTTP流式body限额、preview绑定、SQL原子确认/权限/重放由后续切片实现。导入无效返回products为空不是数据库回滚证据。修订需新精确SHA复审；本审查不要求为了纯片提前启动这些资源。
