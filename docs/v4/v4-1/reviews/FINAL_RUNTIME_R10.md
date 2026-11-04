# V41 r10实际原件分层核收

2026-11-04（台北）。当前结论：`ACCEPT_R10_BUILD_INSIDE_PROOF_CLOSED / RUNTIME_PENDING`。本轮仅核收本案build/sourcecheck与独立关闭，不签正在执行的runtime、SQL、Native、业务截图或视觉；后续仅凭本案实际原件追加。

固定source `261f39904d8cd5a3d6ae070cdca4a7ae5cde4d6e` / tree `34da95131e04d7360ea8aa5250ea40215bcb0713`，见 [组合源码核收](FINAL_SOURCE_261F399.md)。实际image `sha256:e834528d433acaf8ab9c3214d775670e0602d42b906a12ea02ea186b4a783798`，linux/arm64，source label精确为261。base `sha256:69833822bd3ffdece19bea9a2319be11e3935f9e66372395b0bdfdb23cee7288` 的本次前后inspect原件字节相同；未以r9旧image或旧pass补签。

## build原件与inside proof

只读目录 `/Users/aipuli/.codex/worktrees/commerceops-v41-browser-final-r10/commerceops-agent/.audit/v4-1/browser-final-build-r10`。receipt.json独立SHA256 `4909ddc9d6f2f19f4618cfd90f7e54f65bea4b84ee656d3e548b378b4f1ddfe0`；closedfinal.json `781574f9220bc2452ac868555fc6691a35be789395cfd065d41bb46debe5d411`，closed精确引用本receipt。实际build监督UTC10:45:09.317753—10:45:32.648599，独立关闭采集UTC10:45:59.414119—10:45:59.829192。

source_binding中的PREPARED_NOT_EXECUTED是原准备记录，保留不改；实际完成结论来自本次commands/inside stdout/closed。archive SHA256 `f7526d9e27ffe65762d740fe180c70bb9bec67469ea6c3a3e33b45cbb1fd6a55`与已核261完整1858条目来源一致，本轮重新核archive摘要并逐项读取其中runtime字节。

本次rendered Dockerfile.overlay、expected-runtime.json、verify_inside.py三摘要分别为 `d67ec7ee8c72e024b4fbbec1f850c8bcc50a0b2e24093e46f12d923c1863f5ab`、`561d6984f460a246142ab718a98e8f8af78737ad0f108cd80c90afd8fab56d9a`、`20718b7cb02763253c453f6703687d45ceeb666f3d93b9149318a3822c24636e`，全部独立匹配绑定。Dockerfile/verifier与已审固定方法字节相同，但本次源码manifest、实际image、commands及日志独立核对，不借旧执行结果。

独立从261 Git树推导backend/tests/scripts完整集合加pyproject.toml/uv.lock/.python-version，共712文件，精确等于expected-runtime及实际sourcecheck.stdin；逐文件校验Git blob、archive字节和实际build context SHA256相等。其backend/src/commerceops的.py精确子集为216，不只核Root提供的少数inputs。

实际sourcecheck命令绑定本image ID，使用--user501、--network none、--read-only、--cap-drop ALL、no-new-privileges、--rm及容器内python -I；-c脚本与rendered verifier完全相等。脚本核容器内完整runtime文件集/字节并拒链接，随后从真实commerceops import spec定位/app/.venv非editable包，逐.py核完整installed集合和字节。uid501是实际run参数及closed字段，不冒称另有os.getuid独立输出。

实际sourcecheck.stdout与receipt.inside_verification完全一致：EXACT_SOURCE_AND_NONEDITABLE_PACKAGE_MATCH、712runtime、216installed。规范sorted JSON manifest摘要独立复算为 `f01b50b4e531607bf55cb306286cf1d6ede5ddd54d8638e74833db5c27ee9b84`；该摘要与expected-runtime原文件字节hash分列。build及sourcecheck实际native0，无timeout；build同时指定network=none/pull=false。

## 关闭及证据边界

31个原命令的62份stdout/stderr及独立closure6命令的12份日志，74个hash全部独立相符。原27命令native0；new_tag_absent、sourcecheck_absent、remaining_sourcecheck、final_sourcecheck_absent四项为预期不存在检查native1，全部无timeout。最后inspect原stderr明确 `v41-browser-final-r10-sourcecheck` 不存在，未将全部命令改记0。

原cleanup及独立closed的本namespace容器/网络/卷均空，原最终与独立列表stdout/stderr均空，六个独立命令native0。31个登记CLI组与原cleanup/独立closed集合精确相等；原逐组native1/states空。退出结论依据本案两份回执，本轮未追加运行ps，也不冒称拥有逐组原ps stdout文件。base image保留，资源清理范围不扩为全机资产审计。PG_started=false、secrets_created=false只适用于本build阶段，与正在进行的另一个runtime窗口严格分账。

独立静态/原件比对程序native0；未调用Docker、网络、服务、PG、浏览器或重跑build，未读取凭据、Root运行中WIP或另一case材料。本核收没有依赖ROOT_BUILD_REVIEW摘要替代上述原件。Hosted、外部业务和生产未由此执行或核收。

runtime当前PENDING，须由Root随后提供本261/imagee834的完整执行、原键/SQL、Native原图、independent closure等原件，再在本文件追加精确核收；本次不预填任何结果。仅此文档指定changed-file/index预检后普通冻结、不push。

## r10完整实际运行与独立关闭追加核收

2026-11-04（台北）。更新结论：`ACCEPT_BOUNDED_R10_LOCAL_RUNTIME_SQL_NATIVE_EVIDENCE_CLOSED`。上方build-only及runtime PENDING保留其先前时点，本段依据随后实际原件关闭本案运行审查。固定同261/tree34da/imagee834，原case目录 `/Users/aipuli/.codex/worktrees/commerceops-v41-browser-final-r10/commerceops-agent/.audit/v4-1/browser-final-r10`。未拼接r9、lab或Mock结果。

### 原生执行及来源

parent-native.json记录单次实际UTC10:48:49.477572—10:49:58.636838，69.159266秒、native0。execution原状态 `SCENARIO_COMPLETED_PENDING_REVIEW`、原 `summary=NOT_WRITTEN` 均保留；后者是原字段，不将尚未写交付摘要误当运行失败。38条required记录中37条有native_exit且均0，另1条是browser selected2/passed2/skipped0/retries0汇总，不冒38个测试或38条原生命令。

原Playwright JSON仅原两标题：business passed15929ms、Shell passed14301ms，retry均0；整体expected2/unexpected0/skipped0/flaky0/errors空。Node原生退出0、probe0。精确261的validate_report及validate_receipts只读重算结果与execution.browser_receipts完全相等；没有调用测试体、registry、Docker、数据库或重放请求。

source-before/source-after都绑定261/tree34da。1858个tracked hash逐项与精确Git archive核对，9项tool hash和mode前后相同且本轮只读核实实际字节。raw snapshots不相等：唯一差异为frontend/next-env.d.ts由ABSENT变为原批准PRESENT_CANONICAL，296bytes/UID501/0644/hash `0f70629890b72a0a82e91972cc032c04b658b26c265373cb711cf576bfbf8fcc`；执行精确matches_source得到true，未用宽松相等抹除差异。Native内部source/tool前后也匹配。

本runtime case.test_image、实际API容器image和已核build image相同。runtime image_source原stdout再次为712/216强证明；其四项结果与execution一致，execution另加的installed manifest摘要 `e8032e82df7255d598d9119897030899c713cbbb86ad055b3e4a8c78c536b33b` 已由216源文件集合独立重算，不把派生字段冒称原stdout自带。三owner动作依次COMMITTED/COMMITTED/VERIFIED，safe结果7表/7runtime signatures/22private functions、private_verifier_app_read=false；本轮未读owner凭据原日志。

### Shell、业务、mobile与逐key SQL

Shell实际执行原14导航、1440/1280/390及同原visitor create1；offline/navigator false和真实minimized/hidden后的includeHidden敏感DOM清除、同cookie GET恢复及extraPosts0均由原spec PASS和safe回执支持。三次currentFacts trace均EXACT_RENDERED_RESPONSE_VALIDATED，首轮两validated请求匹配ordinal2，后两轮各1；没有按首个或最大时间戳替代关联。真实upstream迟到ACK200保持原body hash，释放点为logout committed且敏感状态已清，送达后仍ABSENT。Shell不代签business KPI，原字段NOT_VERIFIED_BY_SHELL保留。

Shell owned CDP原ACK/页面绑定/closeout/native-exit通过原校验，close_ack=true、原生CFT exit0/signal null、failures空；与Native200的browser exit层次分开。原business journal37行与Shell2行均匹配execution原hash和导入数，errors空。business有11唯一业务key，10个mobile key是其子集，32个business PNG；操作为4标签、1履约、4preview、2导入及1次下载。批量两项的当前页ID/version、不同原key、CAS/revision接续、NativeTiming不等式、写前pending证明、末pending空与进度核收均由同源collector/validator及原材料闭合。没有将事后COMMITTED_READBACK日志顺序当网络时序。

业务真实路径保留SKU筛选/CSV下载、单标签与批量、已记录支付履约/未知支付按钮禁用、CSV/XLSX映射/确认/来源/SKU回读、CSV22行引发真实分页、另一shop及另一visitor隔离。390下执行原UI动作并绑定其POST Request/key/回读，不只截图；三宽8状态与390额外状态共32图。anonymous空态仍只签ANONYMOUS_ONLY_NOT_403_REVOKED。

原final_facts命令native0，DB UTC10:49:56.073267位于命令10:49:54.878134—10:49:56.279617内；API stop及oneoffs结束在之前，down10:49:56.281164在之后。最终revision0025、7表、policy1、6个subject scopes与原export及11个attempts逐项相同。

独立从原journal请求与最终SQL JSON重算严格DTO/body hash、canonical request、scope/key/epoch/generation、receipt/event/effect digest、resource version/revision及import job版本。4preview均唯一PUBLISHED、STOPPED、parse_slot null、reaped true/native0；7个非preview key各有receipt/event，5项标签/履约effect_count各1，两个imports为22与1。当前effect共26行；两次旧标签是REPLACED_BY_LATER_TAG_VERSION，按原请求、同scope template及历史event digest验证，未伪造旧当前行。离线复算调用精确verify_receipt与只返回已采集行的适配器，不执行SQL；真实唯一性与采集时间依据原native0命令，未用适配器冒实际数据库查询。

### Native原图与独立关闭

Native receipt状态 `NATIVE_ZOOM_CAPTURED_PENDING_VISUAL_REVIEW`，真实extension因子1→2、same tab/settings/event、固定外窗1440×1000及只读同Shell身份通过原校验；dashboard行42、products行8，51个允许读取、refused空。五个capture observation前后inner/DPR一致，outer固定、可选zoom本案均存在且前后相等，无detachFailure。五张原PNG均2880×1826；100% DOM1440×913/DPR2，200% DOM720×456/DPR4，因此200%高度为期望1824+2，按原±2边界通过，没有改尺寸或放宽规则。

Native cleanup confirmed、profileProcesses/registeredAlive空，无forced/emergency/closeFailure；原 `nativeBrowserExit=NOT_EXPOSED`、humanVisualAcceptance=NOT_RUN保持，不把进程消失补写成Native原生exit0。Shell CDP的独立native0不能覆盖此字段。

独立closedfinal于UTC10:51:02.810775—10:51:03.868718封存；40个唯一raw PNG路径/hash/长度/签名集合精确等于32business+3Shell+5Native，未编辑原图。本轮核字节及几何，不进行视觉判定；Root转交Terra `c7f508dc596878a327fbc8e175b4e9b369f538a6` 的40/40 AI工程视觉另账，390右列静态限制及human NOT_RUN不由本报告提升。

driver cleanup confirmed=true/failures空；writers原退出probe0/Web0/**API130**原样保留。browser三组forced/remaining空；独立五个组67953/67997/68006/68275/68433均记录消失，owned-case matches空。容器/网络0，端口18479/13479关闭，恰好本案卷v41qa_browser_final_r10_pg_data保留，独立volume_identity原JSON与created_volume完整相等。8个独立inventory/identity命令均0及16份原日志hash相符；进程/端口结论按独立回执，不新增现场ps/lsof/Docker探测。

### 原件摘要、独立复算和限制

| 原件 | SHA256 |
| --- | --- |
| execution.json | `9038347e0018be56370388a156b32f6a4be172fce1ffe77b2af81244c1992357` |
| closedfinal.json | `0df4a06b87110816d449415bd5ad416b885de5d2f8191f10bf5781770462a192` |
| processes/probe.raw.log | `aeba52c845aa9efcc7d6bb9fb9f00fe32a2823b8ff1fb5a93139f129e8a77c84` |
| browser-shell/shell.safe.json | `a53290c74aa5ed36e5d2c045d4386cbbe4c17881ab0cb56cee111b604d8662c4` |
| browser-business/business.safe.json | `5a268291b1883bcc7d95c2b7ff82d450967cd83b5396df1f69c18b9142752216` |
| native-zoom/receipt.json | `1fddab51b1c0809d3dd9c7335577526b2ee2951b279305bcc8283c17f533b15e` |
| final_facts.stdout.private.log | `0e4b6bd35794fbb040a4515f821d6c8ca3a66eba6846f4bfc84605542620dad7` |
| browser-business.subjects.private.jsonl | `ba4d5765924d08ad1b79f2e5ebc49b66e808872e7a9ec88e6f5aacec279f64a4` |

closed列出的15份artifact摘要全部独立匹配，另核54份获准required日志及16份独立关闭日志；跳过compose_config与三个owner原日志，不读取cookie/auth/headers/Secret文件。精确261只读validator、源码seal及SQL/PNG/closure复算最终均native0，校验前后原journal/原件hash不变。独立脚本位于 `/var/folders/hs/czlwyhb553l9_ghpn6byp6v00000gn/T/v41-r10-evidence-review-_702xgcb` 的review-runtime.py、review-sql.py、review-final-bindings.py。

独立脚本初次把tool_sha256的结构记录误作字符串、另一次把带派生installed摘要的汇总要求与四字段stdout完全相等，分别触发本地断言；按原结构读取hash/mode并独立重算派生字段后通过。这两项是review解析错误，不是运行/tool漂移，不改写原案或补造旧检查成功。

本案本地runtime/SQL/Native采集及独立清理现已按实际证据核收；正式QA_RESULTS/MANIFEST/REVIEW等交付文档可随后按冻结材料编写，不因此把已核运行重新标pending。人类验收、Hosted、外部/生产及其他source Gate仍各自分账；没有新Full、旧案复审或资源运行，仅本文件追加普通冻结、不push。
