# V4固定完整blob的merge-copy分类专项审查

日期：2026-11-04（Asia/Taipei）。**结论：ACCEPT_SCOPED_MERGE_COPY_CLASSIFICATION，0 P1 / 0 P2。** 接受本候选5条新公开author绑定及12个固定source/path/blob锚的git-only merge-copy分类；不签完整freeze dir/index/allrefs扫描或其他Gate。

candidate `47bfcba9817d6c1a879f4c282c54e0a9b07be8f8` / tree `a415a72fb21524928642b44a5287dac3288251ce`（parent7ac），仅原7个scanner/config/provenance/tests/事实文件。只读精确提交及ROOT明确提供的发现日志，不读SCAN WIP。ROOT `.audit/v4-0/scan-after-api-47.log`独立读得SHA256 `1b32ec8c7f0eea1011f43532a13aef25ba8115e1c56a7164d0cd185b6c5297dc`，该非最终日志的249个git blocking按真实parents核得5个author和244个merge（12个来源）。不把旧381个全扫发现重写成当前最终扫描结果。

## 核心信任链

approved_v4_merge_copy先要求scope=git、40位source SHA与原生fingerprint自洽；通过真实git rev-list --parents核至少两parent，不信报告自称merge。随后只遍历固定V4_MERGE_COPY_ANCHORS，路径必须相同，分别git rev-parse命中commit:path及anchor.source_commit:path，两者都必须等于固定anchor.blob。固定12个source/path/blob全部独立查Git核对通过。

这不是按任意祖先、共同列名或局部文字推定公开来源。还需匹配既核规则、path、起止行列及redacted Match hash，并真实git show固定anchor源文件，同一位置完整span SHA256再次相同。即使Match因redaction而隐藏原secret字符，整个文件blob比对仍拒绝任何新增秘密或其他位置变动。只有完整已审文件的复制能复用分类；新的author提交不能因blob相同绕过单父拒绝。锚是固定来源白名单，不要求从运行报告提供的任意ancestor查找“某个像的文件”。

允许已登记history和snapshot的不同原生列值作为离散精确绑定，未加入±1容差；页文件原生列差异仍按原条目记录。路径有两个版本的设计/迁移锚也各自绑定完整blob，没有合并成任意版本豁免。

scan仍逐条输出原命中merge commit/fingerprint，classification新增reviewed_public_merge_copy并附source_commit/blob/finding_source/binding_kind/finding_fingerprint；旧exact分类先执行并保留。未知条目仍blocking，未删除原生命中，不把作者新文件按测试目录一律豁免。

## 5个新公开author用途

逐一读取完整span及上下文并核hash：d578 sessions.py:133是capability调用中的csrf_secret变量引用和固定用途标签，没有读取/写出secret实值；31d sessions测试:151是pytest参数类型声明，:170/:197是请求key变量和固定fixture_version；b726 SCAN_a4f.md:28是既有审查文档里的公开SQL字段集合说明。只批准这5条固定位置/source/Match，不批准未来author。

132个原exact记录（20+13+10+89）逐项保留，新增5后137；79旧目录例外逐项保留，新增后84。所有222个检测规则独立解析比较不变，未改regex/entropy/keywords。history_config实际纯函数运行移除39个V4目录blocks后，与7c262fb旧配置解析对象完全相同：222规则/45旧native allowlists。正式扫描命令继续--all --full-history -m --text --no-textconv --no-ext-diff。

原全历史测试把“exact集合相等”改为“exact集合完整包含，且每个额外native finding必须通过固定merge-copy核验”，是本次ROOT明确释放的分类范围变化；不是仅以>=数量通过。每条仍要求旧exact或新严格copy分支，变Rule/File/line/source/fingerprint/Match仍拒绝。

## 独立验证

- 对ROOT原244条对应12个精确merge source分别以source^!、full-history/-m重新原生捕获；原244指纹全部存在，全部通过候选copy分类。没有再扫全--all、没有按当前活跃refs总量猜244。
- 5个原author来源独立有限原生捕获，精确history分类通过，merge分类均拒绝。12个锚source/path实际blob全部相等。
- 对真实命中独立变更RuleID/File/起止行列/Match/Fingerprint共8类全部拒绝；scope=dir/index拒绝；固定锚source/path/blob三类篡改全部拒绝。
- 在Reviewer独占临时Git对象库中，用真实单父/双父commit和精确锚blob构造测试：双父完整复制接受，单父复制拒绝，双父文件其他位置追加一个字节及追加合成secret形状文本均拒绝。finding元数据为已核样本的合成绑定，不冒称这些临时commit来自生产native扫描；Git parents/blob读取是真实的。仅以只读alternates访问原对象，未改原refs、无remote fetch/push。
- 所有临时reports/对象库已清理；原生secret/Match未输出，公开源码片段仅用于人工用途核查。作者首次列差异FAIL、范围185/244误用FAIL和后续有限PASS按原文保留，不被本轮重命名。

## 范围与交接

接受的是固定完整文件复制的收敛规则，不是“所有merge安全”。未来新blob、新author、新path或未知span继续拒绝；ROOT后续最终完整扫描可能仍出现新阻断，应按实际保留。本轮full dir/index/allrefs NOT_RUN，无PG/API/Web/Docker服务/Hosted操作。Reviewer只提交本报告；ROOT可据精确候选安排正常集成和最终freeze扫描，不能用本回执代签最终零blocking。
