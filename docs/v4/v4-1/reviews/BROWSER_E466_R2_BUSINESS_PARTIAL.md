# V41 browser-e466-r2业务单项有限核收

日期：2026-11-04（台北）。结论：ACCEPT_BUSINESS_SPEC_PARTIAL_ONLY；整案FAILED_OR_UNKNOWN保持。只读原件，不启动资源、不重试。

source `e466f03436ba726b6050b10e879da68d80c7e372`，tree `3f1abf65275d01803aca93ec6976453f060ed209`，image `sha256:5818e252fa7978e0c13469d34b0bd275e440e1bcc702737b10eaacaf22fe211e`。证据目录为browser-final-r1工作树的 `.audit/v4-1/browser-e466-r2`。execution/build/business safe来源一致；build记录712 runtime/216 installed proof与execution一致。独立核7个关键spec/fixture/writer/collector源码SHA对应精确Git和运行前后source seal；同e466.matches_source复算通过，raw不等仅按原允许生成声明判据处理，不改失败状态。

原probe报告恰好两标题：business.live expected/PASS、8997ms、retry0/errors0；Shell unexpected/timedOut、240036ms、retry0。报告整体expected1/unexpected1/skipped0/flaky0，probe/Node native1，driver FAILED_OR_UNKNOWN。Shell精确第67行在390宽度getByRole(button,智能助手).focus超时，与原源码执行顺序及safe failure定位一致。只有1440/1280 PNG；390 PNG、shell.safe及native-zoom目录不存在。offline/hidden、Native、lateACK位于失败行之后，全部NOT_RUN，不能从截图文字或cleanup推断通过。

业务部分独立闭合：business.safe与31行原journal/source/hash对应，4条scope记录加9个业务POST各自ATTEMPT_STARTED→ACK_COMMITTED→COMMITTED_READBACK，共31行；Shell另2条scope，共6个最终subject。按同源DTO复核9份原body hash/scope/key并与末态DB canonical请求逐项匹配。4个preview各唯一PUBLISHED、STOPPED、parse_slot=NULL、reaped=true/native0；5份action receipt/event为2标签、1履约、2导入。独立重算receipt payload/hash/身份、event effect digest与当前25行effect payload/hash；CSV22行、XLSX1行。第一标签已由后一版本替换，原receipt和历史event digest按原意图重算成立，不要求伪造旧当前effect。final_facts真实命令native0，revision0025/7表/policy1，执行于停止writers后、down前。

按精确business spec及PASS核收的UI语义限于：dashboard/14日切换、drilldown和非模型助手的严格DTO/scope读回；SKU筛选、实际CSV下载bytes与response相等；两次标签递增版本和after_revision；已记录支付履约及未知支付按钮disabled；CSV/XLSX发现→映射→preview/job/key读回→confirm→来源读回；22行CSV促成真实20条首页/后页/上一页cursor与DOM核对；另一shop及另一visitor隔离。safe计数2标签/1履约/4preview/2confirm/1download与末态相符。这里的9是业务POST，不是全部session/control POST；未知支付只核按钮禁用，不冒真实拒绝POST。该单项也不代签54ab独立金融金标或完整浏览器权限矩阵。

清理单列：execution cleanup confirmed=true，browser forced=[]/remaining=[]/registered group18177；probe1/Web0/API130原样保留。独立closed记录三个目标group消失、owned-case匹配空，容器/网络0、18471/13471关闭、恰好1本案卷保留；创建与最终volume identity原bytes/hash一致。清理通过不提升整个测试结果。闭环所列7个artifact hash均独立相符，未重新查询Docker/进程或打开PNG作视觉验收。

关键原件SHA256：closedfinal `d2ffbc5e15e0809a76f2cb5a5f0958af33d7d86d315e6aa033e9f081ec181271`；probe report `8cd8d4ac5bd8aca28be5294c00d81c7d2d22119591c70eb32ec96ed657f6ca77`；execution `fa71dff68d17b92842ac4da9c3b62d06f99bc2b52e21e7c955cc5d0494a81f79`；business.safe `16350add276cc367449be5966a7bb1557fd4c7f97f0b0b81e5715d761561bd1b`；business journal `b8410845281ef5192c0fa8a1e9716c5610b2ec6eb177772e0d0fb522c07f15af`；final facts `1eadf3139c37490ac09c46ca61d6eb8203655726dc3db72ca832cfa5d4330c76`。

独立校验程序native0，只解析既有获准journal/末态并调用公开纯验证函数；未运行测试体、服务、HTTP、SQL、浏览器或Native。未读取cookies/auth/session/headers原件，未输出私密原body或身份值。后续ARIA源码及其运行另案核验，本回执只属于e466/r2，不重签新SHA、Full或整案PASS。
