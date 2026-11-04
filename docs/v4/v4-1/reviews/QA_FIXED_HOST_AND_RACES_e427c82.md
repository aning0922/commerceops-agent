# V41 QA固定daemon、来源封存与并发候选复审

日期：2026-11-04（台北）。精确提交：`2cfacffb71370a83598c9fac55b51964619c1c4f` / tree `b3765a7a461c5c145b02bd8db9a34b7e955b0b51`；其直接子提交 `e427c82c251fcba4e1b658167ffc1ccad9c9c712` / tree `f30b89b8d24cb2db310cef5e48e5390f691007ab`。范围仅QA driver/recipe/test及必要旧公共helper、validator、observer依赖；未读WIP或后端新候选。

结论：ACCEPT_FIXED_DAEMON_AND_TRACKED_SEAL_PREPARATION / ACCEPT_CLIENT_RACE_RECIPE_PREPARATION / HOLD_ACTUAL_RUNTIME。原daemon调用顺序阻断D03在准备代码层关闭；原D02的tracked Web源码缺口已补，但新增可执行源码仍漏检（P2-D04），最终业务事实部分也未关闭。R05状态语义保持。没有资源或运行授权。

## 固定daemon候选接受

freeze在任何daemon命令及cleanup try/finally之前核Root显式Unix endpoint、Docker binary hash、server ID非空、公开Compose插件绝对路径/hash。新case内建立专属HOME/DOCKER_CONFIG，auths为空，只链接已pin插件；shim每次复核解释器、Docker、插件、config bytes，以execve固定--host及白名单环境，不继承DOCKER_CONTEXT/旧凭据，拒host/context/config覆盖。

driver首个daemon命令仅info核server ID，成功后才镜像/IPAM/Compose模型/空namespace；namespace_initial_empty只在这些检查后置true。静态失败零daemon调用，server ID不符仅一次身份查询且不arm cleanup。public镜像/IPAM、OwnedAdapter、probe子进程fixed_compose及finally均传相同shim；本次没有发现旧implicit-context命令旁路。该修复可以作为准备片接纳，真实socket/server/image/cleanup效果尚未运行。

## tracked源码修复接受，P2-D04新增源码漏检

snapshot逐项核HEAD所有tracked常规文件的实际blob、可执行位、无symlink路径，且index等于HEAD；包含完整tracked frontend、Compose、lock，不再仅核backend镜像输入。另pinPython/Node/Next入口/Docker/Compose文件路径、bytes和mode；终态再次snapshot比较，原已跟踪前端组件脏改现可被拒。

但source_seal.py第17至45行只遍历git ls-tree HEAD。初始Case.validate的git status只能保证开始时干净，终态没有再次检查新增未跟踪源码。Next dev在运行中可发现新app路由/组件；这些实际输入不在任何前后manifest内。

独立纯复现：临时Git仓库提交frontend/app/page.tsx，取before；新增未跟踪frontend/app/extra/page.tsx，取after。git确认有untracked文件，before==after仍为true，repro exit0。driver可继续标TRACKED_SOURCE_AND_TOOLS_UNCHANGED；该字面状态对tracked而言成立，但不足以签完整host Web来源。

最小补齐：封存并核实际运行源码目录的文件集合，拒运行期间新增/删除/替换的代码输入，或终态显式拒所有未批准的untracked源码。明确排除.next等生成输出及已绑定依赖目录，不把正常输出误判为输入；不能仅扩大README中的unchanged措辞。现有README对未跟踪依赖没有供应链审计的限定是合理的，但新app路由属于源码，不能归作依赖审计范围外。

## 同key/异key并发准备片接受，证据限客户端并发

pair确实建立两个真实httpx.Client，各自独立CookieJar并深拷贝同一当前session；线程池两worker在Barrier后调用固定POST，transport retries=0。没有以串行两次调用或mock返回冒充并发实现。每个POST独立随机request journal，发前持久原payload/UNKNOWN，ACK再更新本文件；subjects以文件锁保持operation/key观察历史，不再共用pending文件互相覆盖。

同key要求两个COMMITTED且整receipt相同；异key同revision/version要求一COMMITTED、一明确VERSION_CONFLICT或SNAPSHOT_CHANGED。随后读取两个原key，winner精确receipt、loser UNKNOWN且不POST；商品版本仅+1、tags来自赢家、其余字段不变、scope内receipt/event各+1而现存tag行数不增。该断言与当前标签更新模型一致。

Barrier只同步客户端起跑，之后仍有journal/registry与调度；没有请求开始/完成区间或服务端屏障。故即使未来该recipe运行通过，也只能签这次双客户端提交及结果，不能自动证明PG临界区重叠、具体锁交错或撤权线性化。README已明确这一边界，本次不把它另报为代码阻断。若要关闭实际事务竞争Gate，需要另有精确请求区间和/或既定服务器/PG屏障的证据，不用两个future存在代签。

## 未关闭的运行门槛

D02最终业务事实：driver停止writers后仍调用pg_observer schema --final；其结果为版本、七表集合、policy行数和DB UTC。subjects虽预先登记scope/key，但没有消费到末态tenant/operation/key/receipt/event/版本/库存事实采集。中途counts与catalog-races私有JSON不能代替writers退出后、PG关闭前的最终对象事实。

R05：Business.call第204至216行仍只核schema、HTTP expected、no-store与context；普通业务读未要求envelope.status=OK。validate_response也只做闭集schema，允许合法UNKNOWN。并发receipts函数自己明确要求COMMITTED，这是局部正确，不能代签其他recipe读状态语义已修。合法原key UNKNOWN路径必须保留，不全局禁止UNKNOWN。

runtime handoff与grant CLI仍是明确预留接口，缺失在daemon前拒绝；不能用占位文件解锁。尚需最终API/SQL安全修复、精确schema/grant/owner policy接缝、真实build/source receipt、Root资源/UTC及实测清理。此次修复不解除后端业务HOLD，也不将sourcecheck镜像程序或stand-in命令当真实Docker证明。

## 独立验证

精确e427 git archive隔离执行test_fixed_daemon、test_source_seal、test_owned_driver、test_concurrency_recipes、test_subjects：11 passed，native exit0，3.85秒；六条隔离offline marker warning保留（含导入fixture模块）。使用临时Git及本机短stand-in可执行程序核argv/env/顺序，driver端口函数为mock；并发测试仅合成回执判定与本机metadata锁。新增untracked源码复现亦exit0。未运行execute真实资源路径、Docker、PG、网络HTTP、浏览器或远端操作；没有修改候选实现。
