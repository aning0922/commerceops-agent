# M3公开整行扫描增量候选（2026-11-03，台北）

基线Root `ac6edf24515aa2148037aa24a84d0618f1e30f74`，独立worktree
`commerceops-m3-scan-public/commerceops-agent`。仅扫描固定来源/快照检查、生成规则/provenance和必要测试。
不改业务、runtime helper、scripts.check、CI、权限或服务。

## 分类与固定源

Root完整扫描原记录native1保留：dir15blocking、index15blocking，Git156项中20项旧精确审批和136blocking。
本轮没有重跑Root完整可达历史。只读安全元数据日志SHA256：`11f13a58424d0e1dddc7f1c55401a4d2c239480c132cb6907c0e2a7aecd5a9c1`。

逐条读取166条blocking记录对应的实际Git源，起始行内容归并为15个路径/内容组合。
分类均为公开代码：DDL UUID字段、请求键/候选hash的变量传参和TS响应验证、指标枚举、pytest类型注解、生成资产SHA256。
未发现凭据字节；没有把文件名或keyword本身当作公开性的证据。两版checksum已分别重算同commit实际资产blob验证。
原Secret/Match和原扫描报告不在本文重放。

18项新绑定包含当前多个独立行位、未来集成文件的明确pin、两个不同历史整行及一个严格两完整行span。
历史同path/整行的多commit重复不新增宽匹配。tests/test_m3_copy_app_pg.py在ac6不存在；其当前候选pin来自明确f20提交，
不存在不强造文件，后续出现仍须准确行位/hash。旧版typed参数行只作历史整行规则，不放宽当前pin。
旧checksum也只作历史整行规则；当前第5行换成旧checksum会被快照拒绝。

| 范围 | 固定源commit | path | 行 | 完整内容SHA256 | 公开语义 |
|---|---|---|---:|---|---|
| current pin | `ac6edf24515aa2148037aa24a84d0618f1e30f74` | `backend/src/commerceops/entrypoints/knowledge_copy_http.py` | 218 | `e03dae298ac58f76d1e2323a5983ffafe10c5062e0dc6e1c52aacd26f38427bc` | 请求键与候选hash变量传参 |
| current pin | `ac6edf24515aa2148037aa24a84d0618f1e30f74` | `backend/src/commerceops/entrypoints/knowledge_copy_http.py` | 229 | `c4c65eb64554649746e6cd17210ab907d2b3613af434dc3bf30e68161b0d8d91` | 请求键与候选hash变量传参 |
| current pin | `ac6edf24515aa2148037aa24a84d0618f1e30f74` | `frontend/lib/p6-inquiry-client.ts` | 123 | `32d3ade5904ace51ba00499406316ec09cca2c53103c6f32b3817065ed665181` | 公开请求字段/响应类型校验 |
| current pin | `ac6edf24515aa2148037aa24a84d0618f1e30f74` | `frontend/lib/p6-copy-client.ts` | 46 | `32cf2c9499c2b9f86c23973c9dd6794693eb20408577d687c531a0af19bd5fc3` | 公开请求字段/响应类型校验 |
| current pin | `ac6edf24515aa2148037aa24a84d0618f1e30f74` | `frontend/tooling/check-p6-daily-s3-schema.mjs` | 5 | `879663a25802cf1a8ea527dc2b34b5ac0948ca2fd4c620be60f57124bebe9478` | 同commit生成资产SHA256（已重算） |
| current pin | `ac6edf24515aa2148037aa24a84d0618f1e30f74` | `frontend/m3-tests/daily-s3.fixture.json` | 72 | `9761f2d4abc97c05a69bdd1c48a5e9ec572973bc8d347a90f0163dd4aebe7dd2` | 确定性日报指标枚举 |
| current pin | `ac6edf24515aa2148037aa24a84d0618f1e30f74` | `frontend/m3-tests/daily-s3.fixture.json` | 169 | `9761f2d4abc97c05a69bdd1c48a5e9ec572973bc8d347a90f0163dd4aebe7dd2` | 确定性日报指标枚举 |
| current pin | `ac6edf24515aa2148037aa24a84d0618f1e30f74` | `tests/test_m3_local_runtime.py` | 191 | `1560f72d6e586424aa2a01bccb1c4de0a4aadbe00a4740c4b55c8b1d2f2e2a68` | pytest fixture参数类型注解 |
| current pin | `ac6edf24515aa2148037aa24a84d0618f1e30f74` | `tests/test_m3_inquiry_wiring.py` | 102 | `41c11ee208d8c300f6f27de3e3265c6c3899daf4244e6d1abd925aab4c240ada` | pytest fixture参数类型注解 |
| current pin | `ac6edf24515aa2148037aa24a84d0618f1e30f74` | `tests/test_p6_inquiry_pg.py` | 602 | `01877a828b93d29e948eebd5a18fbd1219da0791cc0e12ddc9a873167fa6e47b` | pytest fixture参数类型注解 |
| current pin | `ac6edf24515aa2148037aa24a84d0618f1e30f74` | `tests/test_p6_copy_pg.py` | 172 | `ce347dbf648728b418aa6fa7e32c357927ff5b865a06507e9bdfe4363a80c2ab` | 请求键与候选hash变量传参 |
| current pin | `ac6edf24515aa2148037aa24a84d0618f1e30f74` | `tests/test_p6_copy_pg.py` | 348 | `acc74328a284ec6eead7a636ebb20716c2048dbd7f8e05d8df40934c7245ffca` | 请求键与候选hash变量传参 |
| current pin | `ac6edf24515aa2148037aa24a84d0618f1e30f74` | `tests/test_p6_copy_pg.py` | 354 | `ce347dbf648728b418aa6fa7e32c357927ff5b865a06507e9bdfe4363a80c2ab` | 请求键与候选hash变量传参 |
| current pin | `ac6edf24515aa2148037aa24a84d0618f1e30f74` | `tests/test_p6_copy_pg.py` | 369 | `acc74328a284ec6eead7a636ebb20716c2048dbd7f8e05d8df40934c7245ffca` | 请求键与候选hash变量传参 |
| current pin | `f20dadf10511116e5d67ecc6f841d1e375009a1e` | `tests/test_m3_copy_app_pg.py` | 31 | `9fe7174fdb0526dcf7548af9e7f992bd4cd6da2d2969025200412fc5c748ecc7` | pytest fixture参数类型注解 |
| history only | `4c6d601b9b5b54010e6004993bd710613fdf9a3a` | `tests/test_m3_copy_app_pg.py` | 27 | `1782394b2da3adb48a0fdcfd478ea67663d4f7d02e90cac840fb061576347b49` | pytest fixture参数类型注解 |
| history only | `ba5c550d56ccb9c3ff141018a96719316787857e` | `frontend/tooling/check-p6-daily-s3-schema.mjs` | 5 | `ff43a3b2ff169e391094eb4d00854cfdfa6b4b367666ae6761dc9eb9c3ec3037` | 同commit生成资产SHA256（已重算） |
| current exact span | `ac6edf24515aa2148037aa24a84d0618f1e30f74` | `backend/migrations/versions/0023_p6_copy_drafts.py` | 34–35 | `96ce803f7ab588bddd5838a711219fab5becdb93daac2cf3803dcf0f99b5b510` | UUID/请求payload/hash列DDL |

0023的实际gitleaks匹配跨34–35行；安全日志仅记录起始34。
该例外只接受两条完整原始行与一个LF，使用既有逐ASCII字节regex形式且首尾锚定；
provenance另固定source_end_line=35，当前/index同时核两完整行组合hash。
没有单独宽放起始片段；改动第二行、追加内容或移动span仍拒绝。

## 规则与验证边界

固定上游配置从本机既有缓存读取，SHA256核为e163e53b9e7e8a8511e77271e2b323ed057759542a6d988258afe3a1fa329caf，未联网。
生成222rules/44exact exceptions；前26exceptions（含原17及原9 M3）逐项相等，20项历史审批逐项相等。
将新增18allowlists去掉后，全部原规则TOML语义与ac6完全相等。其他规则、global/secret/path宽豁免均未加入。
新项均generic-api-key、AND、严格完整仓库相对路径和完整原始内容；历史两个不同版本各有独立commit/line/hash。
生成器和验证器均核固定源，source_end_line或span hash不符拒绝；current guard只核当前pin，不把历史版本当作当前任选值。

实际定向验证34passed/180deselected/native0（含两行低熵/移动/截断及无.git收集），日志仅本地工具回执：
当前新公开源文件的native dir0、从实际staged blob复制的index快照native0；
独立小仓库五个合成commit（当前、两次旧版/恢复）native git0；18项逐项整行/第二行变更native1；
嵌套路径native1，邻接/同行生成token native1；旧9项逐字节regex与缺固定源fail-closed仍通过。
未运行Root全历史；34通过不能转签原完整scan失败。所有166条blocking源记录另经实际commit/path/line/hash对照核验，
当前全部tracked路径的固定pin检查0违规。

开发失败保留：首轮18pass/2fail/6.90s，因DDL实际跨两行使单行规则不足，改成严格两完整行span后20pass/7.85s。
一次静态检查两个Path/str循环变量推断错误已修，未放宽类型/扫描规则。
本候选仍待原独审和Root完整current/index/reachable-history原生扫描核收；没有PG/build/服务或真实provider访问。

两条完整DDL行的独立SHA256（组合hash见上表）：

- backend/migrations/versions/0023_p6_copy_drafts.py:34，`60c387e56bc80ada74f4161dc17d3e1dada2d4ae1fa0dd04dc1b4bc5b351713a`。
- backend/migrations/versions/0023_p6_copy_drafts.py:35，`873a36c7da9ea71339cafd2b412b2e2bebf2487173cbe7b4e59dc36cde9a62b5`。


## 无.git镜像收集边界

两扫描测试模块原先import时调用m3_public_rows(ROOT)，在无.git镜像中连integration收集都会失败。
本候选改为缓存的延迟pinned_rows函数，只在实际offline用例执行时读取固定Git源；
固定commit/path/line/hash及原全history扫描校验不删、不skip，也不吞ImportError。
新增真实子进程在无.git的完整最小依赖拷贝目录执行pytest -m integration --collect-only，
仅收集integration sentinel并正常退出0；两offline扫描模块被正常导入后按marker deselect。
开发中无.git fixture首遗漏repository_files依赖导致收集2错误，补齐实际依赖后通过；
一次延迟命名与原局部rows变量冲突及插入位置的静态错误已修，记录保留。
