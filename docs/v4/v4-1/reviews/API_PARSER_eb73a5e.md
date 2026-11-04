# V41 XLSX样式与压缩异常P2关闭复审

日期：2026-11-04（台北）。source `eb73a5eda3e94368009882ce437dc9e8760cec75`，tree `73fae1bd9a31aedb775f3525dc1ed79570fd568a`。读取imports.py/test_imports.py精确修订；相对ec0ccf2的parser差异只为本次两问题补强，preview父链沿用独立已审bb05695。

结论：ACCEPT_BOUNDED_PURE_PARSER，P2-I01/P2-I02在本源码关闭，无新增阻断本纯切片的P1/P2。Root可合入纯parser/policy链；不签完整导入、SQL权限/并发或硬2秒终止。

## I01：样式语义与numeric词法

新增_styles先解析受限样式：严格sheet namespace、根、group位置/不重复、条目数量与声明count一致；每组最多128条。所有xf只接受General numFmtId=0，拒显式numFmt及日期/百分比/复杂格式，包括style0。font/fill/border/xf索引为有界整数且须落在允许集合；sheet所有类型的style引用都要落在解析的cellXfs数量内。不存在styles.xml时仅允许隐式General索引0。该限定子集不宣称支持完整OOXML样式。

numeric有v值时必须符合非负有界十进制词法（最多14整数位/6小数），不把非数字SKU、指数、NaN或超精度当文本。inline/shared-string保留原明确读取方式，后续字段映射/价格规范化仍执行。空白numeric与缺必填字段由质量规则另处理，不补造0。

## I02：解压异常安全边界

_archive明确捕获zlib.error并转FileRejected固定XLSX_ARCHIVE/from None，原BadZipFile/CRC/截断等拒绝保持。不会将压缩失败当空表或部分READY结果；固定错误不包含原压缩内容。该修复不放宽ZIP/节点/字节预算。

## 独立实际验证

从精确eb73a5e git archive提取backend/src及test_imports.py，在临时目录以locked Python执行原parser模块测试：43 passed、0.10秒、native0。测试实际使用内存CSV/OOXML字节，含General样式1正常数字、inline/shared string、原numeric非法内容/指数/NaN/超精度、style0日期14/百分比9/自定义165、无效style/font引用、DEFLATE/CRC/截断固定拒绝及原CSV/XML/ZIP边界。非实际网络或文件执行mock。

另独立构造7项真实工作簿负例：style0格式14/9/165分别返回UNSUPPORTED_CELL_FORMAT；cellXfs声明count不符及fillId/borderId/xfId越界分别返回XLSX_STYLE_REFERENCE。此前导致READY价格45200的style0路径现拒绝；同类非法numeric由实际测试确认拒绝，损坏DEFLATE不再逃出zlib.error。

隔离目录未加载仓库offline marker注册，出现一项PytestUnknownMarkWarning，原样保留，未为警告额外重跑。本次43项及7个附加反例不冒充作者累计74pure或全工程检查。未读取作者WIP。

## 后续不变边界

ParseBudget仍是协作式检查，硬截止/子进程停止reap、父/锁连接失联fail-closed容量、HTTP流式大小、preview可信映射绑定、当前币种/累计额度、权限及整批SQL回滚均须后续精确候选和运行证据。只接受General受限XLSX，复杂合法Excel格式可以明确拒绝，不能为兼容而静默解释为金额。ec0ccf2失败反例及审查HOLD保留原时点。

Reviewer仅运行纯内存解析与临时源码测试，无PG/API/browser/外部网络或真实业务数据写入。
