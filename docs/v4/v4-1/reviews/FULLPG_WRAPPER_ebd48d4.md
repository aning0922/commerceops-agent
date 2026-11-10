# FullPG私有wrapper最终专项独审

2026-11-04（台北）。结论：`SOURCE_ACCEPTED / BOTH_P2_CLOSED / NO_NEW_P1_P2_FOUND`。最终入口为GATES私有 `.audit/v4-1/full-wrapper-v2/full_gate.reportzero.py`，SHA-256 `ebd48d4f36412d0b91902b9a937940c87a6160220c9cee3f2186656206c20d4a`；reportzero freeze摘要 `7578d41bea3fb614473a3e6a31a725034b08ba290e85bc0111cc58162a483872`。本报告只接受该私有执行器源码，不是FullPG运行回执或资源GO。

原工程wrapper `87aae194f5ee5d0612047c554e2d69fe71698b7eeafb525063d54b94c98cf63a`保持；PG首版f27、runtime修订2a及其失败边界和模拟原件均保留。独立AST对比确认：87→f27仅原environment/worker/launch/main四函数必要接线改变，其余10函数相同；f27→2a仅pg_environment和SHIM改变；2a→最终ebd除SHIM literal外完整AST相同。没有修改正式helper、Compose、业务、锁或监督/预算逻辑。

已核Root daemon JSON精确字段、raw hash、0600/UID和工具路径/摘要，socket类型/UID/mode/device/inode，以及python实际解释器绑定。每case新HOME/config/plugin链接/shim PATH，环境不继承旧Docker context/凭据；每调用固定binary/plugin/config/socket检查、绝对Docker路径与显式--host、server ID info核验、exec前再核。禁止daemon override且原psql -c仍可用。launcher与直接worker均装载相同冻结环境，worker自身clear/update覆盖无显式env参数的prepared_image调用；官方pg_diagnostic的环境白名单仍经过shim。

第一项P2来自f27固定exec环境丢弃helper新增COMMERCEOPS_PG_RUNTIME_DIR。独立核官方冻结源码的实际布局为Root/runtime/p123-12hex，先登记issue23-ci/round-1.json再prepare；compose.yml两凭据缺变量会回退runtime/pg。最终版本只转发经canonical路径、0700/UID、两文件no-follow regular0600/nonempty元数据核验的这一变量，不读取凭据内容。首次报告核project/volume/session/round/started/deadline后，以O_EXCL/0600/fsync写本case claim；冻结Root/source/tree/scope/三UTC及报告dev/inode持续同绑。Compose缺变量拒绝，无变量仅允许image inspect，不退回默认context或默认凭据目录。

第二项P2来自2a对已绑定报告仍要求非空，不能兼容原save的同inode truncate窗口。最终版先核非空私有claim并解析，仅已有claim时允许报告size0；最终仍要求claim全部字段与报告dev/inode精确相等，exec前再核。首次空/不完整报告不能建立claim，两凭据及claim仍必须非空，权限和路径要求不变，没有新增等待、重试或续预算。原f27缺变量与2a零字节拒绝的历史事实不改写。

独立核冻结文件摘要、源码与SHIM语法；在Reviewer隔离目录以普通文本stand-in和socket/server/exec注入复跑2a的21场景及最终9场景，均通过。最终9场景回执摘要 `3238fbfc5d6405ad07d6e08d2e6845a89eadc9b49a840d640a0de9ac694a3535` 与冻结原件相同，明确对比旧2a拒绝/新ebd允许同inode空报告，同时验证首次空或halfJSON、空owner/app/claim、0644及替换inode拒绝。原f27的22项仅核其冻结原件与测试源码，不冒称Reviewer重跑22项；上述注入数字不相加为真实运行矩阵。

原300秒命令、35分钟安排、75秒helper reserve/60秒cleanup及G1/G2不因本修复放宽；源码接受不证明实际容量足够。原父/worker监督、非零/timeout/cleanup未知保留、独立项目inventory及两线pair仍为必要后续证据。此wrapper源码阻断已解除，可供Root针对最终精确candidate、fresh daemon/tool/socket/server绑定、两线UTC和资源排程作实际GO；不复用旧窗口，不代签浏览器closure、实际工程测试、Full或阶段完成。本Reviewer实际Docker、socket连接、PG、build、服务、真实exec及真实凭据读取均0。
