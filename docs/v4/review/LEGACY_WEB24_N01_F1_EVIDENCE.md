# F1 legacy Web24与N01six实际回执独立核收

日期：2026-11-04（Asia/Taipei）。**结论：ACCEPT_LOCAL_LEGACY_WEB24_AND_N01_SIX。** 真实本地API/PG/browser回归可核收，commerce source为mock-fixture；不是实际商家平台/SDK验收，M3 daily/inquiry/copy三条独立flow live仍NOT_RUN。

实际source均F1 `047a43dafef90edea2eb532c2a03b6f850da0b9a` / tree `5c0699edb2d30889ce770ca9b05b56dab957ce10`。运行目录分别为 `/Users/aipuli/.codex/worktrees/commerceops-v4-legacy-web-20261104-047a43d/commerceops-agent` 与 `/Users/aipuli/.codex/worktrees/commerceops-v4-n01-20261104-047a43d/commerceops-agent`，审查时HEAD仍F1。只读安全window/result/cleanup/source manifest、live reports及PG invariants，未读取账号配置/密码/cookie/DSN，未重跑服务。

## Web三段

依据 `.audit/legacy-web-live-20261104-047a43d` 的result及各window，以及 `frontend/evidence/b04-live` 对应read/write/items原报告，独立核 **read7 + write10 + items7 = 24 passed**；标题无重复、位置对应F1实际spec行，报告全部状态passed。read私有目录的独占report与发布副本JSON相同。

| 段 | 原报告duration_ms | window native | PG invariant | 原完成UTC |
|---|---:|---:|---|---|
| read | 37621.637 | 0 | passed，低权/0模型调用/原source completed | 18:00:35.192381 |
| write | 332666.253 | 0 | passed，批准/拒绝/ACK/撤权/过期/旧版本等逐项效果 | 18:06:26.814898 |
| items | 335962.427 | 0 | passed，20项/2000单位、4终态、单次版本/receipt/audit/projection | 18:12:28.485857 |

UTC日期2026-11-03，对应台北11月4日02时。三段source_files_sha256每段20项全部独立与F1 Git原文匹配；同一production build标识由window记录，未用其它tree的生成物代签。source_mode为live-api、identity_mode为session、commerce_source_mode为mock-fixture。实际provider_calls均0；不是把mock商业数据说成真实外部平台。items还记录原native_zoom验证passed，未将其替代V4新Q16证据。

result三段passed/test_exit0/invariants_passed与window一致。每段stopped、PG running=false/PID0、volume保留、owned listener无剩余；外层legacy-web-cleanup逐project核containers/networks0、登记PID和监听端口为空，各卷1。原children停止阶段-15/143保留，其余命令及test原生0；不把停止值改写为全0。

## N01六项

依据 `.audit/n01-live/window.json`、source-files.safe.json、n01-cleanup.safe.json，以及 `frontend/evidence/p4-c09/n01` 原live-results/pg-invariants。报告 **6 passed**，duration45293.356ms，test_exit0/window passed=true。六标题与实际F1 spec行一致；source manifest原字节hash等于window绑定，445项内容hash全部与F1 Git对象一致。

PG invariants与六个report标题一一对应：五项business_unchanged=true；唯一显式创建项为explicit_pair_only=true，不把该项误记零写入。真实parse取消/缺项/异常输入/迟到响应/显式唯一pair/ACK原键读取与同文去重/真实409/撤权拒绝由固定成功spec及PG材料支持。worker_started/sdk_provider_started均false；没有真实provider流程启动。

原完成UTC18:21:38.595551，外层cleanup于18:21:49.290325确认containers/networks0、登记PID/监听端口为空、PG false/PID0、保卷1；child退出0/0/-15/143/0保持原样。source、project、build与window相符，不拿其他历史fixture报告补本次六项。

## 指纹及范围

Web每段原report字节与原window字节顺序拼接SHA256：read `602991ea7829ba39a044b235f6b009a10b02f86f52c50a2f5855de40a46ae166`；write `c5810d4ddac9bdae97e6ae0a0e4c3001cbde3d47722708bf9d31d82f8ed00ab8`；items `31198b368c81e9297c597e35e6dea5558f4e42a74c4b6e11af2d23a9999bc9aa`。N01 report/window/cleanup依次拼接SHA256 `3ac5a211cfc9b0ffc9d40f08325cbd36a648315c2d090bd2ca8606969d2f8b6f`。

本次只核这两套既有回归，不宣称M3日报、询单、copy各自独立live flow执行。F1/R2/R3及审查时ROOT cbd1的backend和产品前端子树相同已另独立核对，但这30项实际source仍记F1；ROOT工程全检与PG双线另交独审，不由本报告预填成功。
