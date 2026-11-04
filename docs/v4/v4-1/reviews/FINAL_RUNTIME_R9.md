# V41 r9 分层运行回执独立核收

2026-11-04（台北）。当前仅核收 **build与容器内源码证明及其关闭**：`ACCEPT_BOUNDED_R9_BUILD_AND_INSIDE_SOURCE_PROOF_CLOSED`。不核未来r9业务运行、PG/API/browser/Native或视觉，不释放新资源窗口。

固定 source `fbb29a429b7f680328ab4451a717adb3ad2d99c1` / tree `ef6d8230ac4b58401af2771d722064aadacc5eed`，继承 [最终组合源码核收](FINAL_SOURCE_FBB29A4.md)。实际新image为 `sha256:07e5483491f36f795ae6bd22e0fd764d8e69090842127887054a93e2a68f2ca6`，linux/arm64；source label精确为fbb。base image `sha256:69833822bd3ffdece19bea9a2319be11e3935f9e66372395b0bdfdb23cee7288`，前后inspect原件字节相同。本轮没有现场查询Docker或改变image/tag。

授权原件目录 `/Users/aipuli/.codex/worktrees/commerceops-v41-browser-final-r9/commerceops-agent/.audit/v4-1/browser-final-build-r9`：receipt.json SHA256 `56e16a2f0ac2e01e51375e5d4297d8a52c4a57b4d0b777a89ce034eccd24a8c8`，closedfinal.json SHA256 `d9eae3ce32da38a2e162576a5c218dae4b6195a2217176313457e978e3f30801`。两摘要独立复算且closed精确引用原receipt。原build窗口实际UTC10:06:36.928230—10:06:59.237276，独立closed采集UTC10:07:28.805384—10:07:29.150045。

## 来源与强inside proof

source_binding仍保留准备时 `PREPARED_NOT_EXECUTED_NO_RESOURCE_WINDOW` 字样，本轮以实际commands/inside/closed判定build完成，不改写该历史准备记录。绑定archive SHA256 `aa3b0733062b6731d0b7703fe13dd92d7fc889bf8b30fbd5600c64e82ecfa36a` 与前轮fbb全1844条目核验来源一致。

独立读取实际rendered Dockerfile.overlay、expected-runtime.json、verify_inside.py，摘要分别为 `d67ec7ee8c72e024b4fbbec1f850c8bcc50a0b2e24093e46f12d923c1863f5ab`、`a14c420dde5d95ccff2ae70471d47add2579767ba2776f8bb66e55a0b834ccf7`、`20718b7cb02763253c453f6703687d45ceeb666f3d93b9149318a3822c24636e`，均对应receipt。Dockerfile先验原锁/Python3.12.13，再替换backend/tests/scripts，通过原uv frozen/offline/no-editable重装本包，未以旧site-packages代新源码。

expected-runtime与实际sourcecheck stdin内容完全相同。独立从fbb Git树重算其完整允许集合：backend/tests/scripts全部文件加pyproject.toml/uv.lock/.python-version，恰好712项；逐项与实际context字节SHA256及Git blob相等，没有缺漏/额外项。216个backend/src/commerceops Python文件是该集合的精确子集。

实际sourcecheck argv使用上述固定image ID、`--user 501`、`--read-only`、`--network none`、`--cap-drop ALL`、`no-new-privileges`与容器内 `/app/.venv/bin/python -I`；执行的-c脚本与rendered verify_inside.py逐字节相同。脚本遍历容器内完整runtime集合、拒链接、要求等于stdin；再从实际commerceops import spec定位 `/app/.venv` 下非editable安装包，遍历所有.py并与216项源集合精确比较，拒链接。uid501来自实际docker run参数及独立closure字段，本轮未把它冒充另有os.getuid输出。

sourcecheck.stdout原JSON与receipt.inside_verification完全相等：`EXACT_SOURCE_AND_NONEDITABLE_PACKAGE_MATCH`、runtime712、installed216；其manifest摘要 `4da4c3bf79a0d622d1aeefda6912b9941390ca7c5f637f70dde1952793218904` 已按sorted JSON重新计算。这个规范化摘要与expected-runtime原文件字节摘要不同，二者分列，不混用。实际build/sourcecheck均native0、无timeout，且不是仅metadata/source label证明。

## 原命令与关闭

31个原命令的62份stdout/stderr原日志hash全部独立匹配；独立closure6个命令的12份日志同样匹配。四个原native1分别为new_tag_absent、sourcecheck_absent、remaining_sourcecheck、final_sourcecheck_absent，属于预期对象不存在检查；其余27命令native0，全部无timeout，不声称31命令均0。最终named sourcecheck inspect的原stderr明确该container不存在。

原cleanup和独立closed均记录本namespace容器/网络/卷为空；独立六命令均0，三类最终列表的stdout/stderr均空。31个registered CLI group与原cleanup absent记录及独立closed列表集合精确相等；原cleanup每项native1/states空。group退出据两份回执核收，本轮没有原ps逐项stdout独立文件可追加重算，也未重新运行ps。原receipt PG_started=false/secrets_created=false，此范围没有启动业务PG/API/Web/browser或生成运行Secret；不扩称全机资产审计。

本轮独立比对程序native0。一次只读定位误将Dockerfile路径放在context根而得到FileNotFoundError，随后按实际build argv定位prep/rendered核对成功；这是review读取路径错误，不是build失败，也未触发重跑。未读docker配置、凭据或后续runtime材料；只读获准原件与公开源码，未调用Docker/网络/服务/PG/浏览器。

此build已独立关闭、image源码证明可供Root后续准入判断；后续实际runtime、原键/业务效果、Native、清理及视觉需各自新回执，不由本文件预填通过。仅本审查文件指定预检后普通冻结、不push。
