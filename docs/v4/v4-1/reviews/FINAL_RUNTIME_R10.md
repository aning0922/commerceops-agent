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
