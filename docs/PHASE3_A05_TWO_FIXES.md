# A05 两项有界修复核收与正常集成

2026-10-11，Root核收原A恢复测试与原B Linux only-owned查询修复的精确源码独审，释放同WT62c8/`codex/phase3-approval`/[Draft PR37](https://github.com/aning0922/commerceops-agent/pull/37)一次正常最终集成push。本页是前次失败之后的新候选；阶段仍in_progress，最终当前四CI/main/同main合后CI/Issue33均pending，不预写通过，也不以旧历史337或Mac24替代本次。

## 972实际失败保持

[CI38086696815](https://github.com/aning0922/commerceops-agent/actions/runs/38086696815)实际checkout `b4d837a56acf3bb15fd227d5f39cce3e20bfddb1`、tree同972的3d4f46：旧236/G1三/G2六/cleanup0成功，P3首审批28actual complete collection中27passed/1failed/265.02s，后73not_run；before_prepare-False call6.7587s，command_exit1/timed_outfalse/stopping_confirmedtrue/cleanup0，pg-pair正确拒绝失败分区。原CI具体assertion trace未捕获，根因unknown；有界probe证明测试观测竞态可达，不称已彻底复现CI根因。frontend B04 offline原lsof3490 beforeAll首失败/7not_run、正式三stage未启动，同次前序schema/contracts/type/build/Mock13不抵完整frontend失败。972最终增量Review5480825374无阻断亦不抵实际失败。

原2e0 before_graph失败及748最小修复、052/a65独审与两个完整337绿CI、333/988作者证据、旧失败/取消run/Review fullcheck not_verified和Issue23 not_identified/risk_accepted继续保留，见[前次集成](PHASE3_A05_INTEGRATION.md)、[恢复实证](PHASE3_A05_RECOVERY_FIX.md)及B原UX交接，不复活旧授权限制或改写历史。

## 两项精确修复与独立审查

| 修复 | 精确source/tree与范围 | Root已核独立实际结果及边界 |
|---|---|---|
| A恢复测试同步 | `087c3b6efd2e0cee034291e3d01623991c8a6f56` / `f82b2bbf627b5aeaae72777c1ea162c0dc34b8aa`，parent972；唯一可执行diff为同失锁测试27+/1-，backend不变 | 原Core无P1/P2，完整19actual PG/94.91s及19pure/0.89s，严格after_t2_commit gap→原wait_ready→官方durable waitCP/旧core/job/count断言及负向三态保留。Root实读safe-summary/pytest19日志，Docker核PGfalse/PID0/exit0、UTC21:37:31.478停止。外层zsh使用reserved status变量导致wrapper1发生在pytest容器exit0之后，不能宣称整个wrapper0；原CI assertion trace仍unknown |
| B Linux owned listener | `849c3eb31cb177d97a3e13c40e139ff2beb9ad4b` / `205632dc4ee41f2dd43b470c39bcdfbc3b4db7c2`，parent972；16个only-B文件=9code+UX交接+6安全证据，产品app/components/lib/public与locks不变 | 原WebReviewer无P1/P2，27contract/type/build/owner10/Ruff，自有Linux ARM完整Mock8/22.1s，wrongcwd/launcher实际拒绝。两次host node_modules缺Linux SWC而0test的准备环境fail1保留；随后在原同22:08UTC截止内公共registry固定锁npm ci --ignore-scripts/build（lock无变化），断网/无hostports Mock8成功。Reviewer报告4自有容器已停：两个准备环境fail1、setup/test0；Root停止回执核对另行记账，不预写全部核收 |

A作者新owned PG固定UTC21:20:41→21:50:41，原node1passed/5.11s未复现CI，单次controlled probe及第二轮19PG/88.27s、19pure/0.67s已独立记账，UTC21:27:59.605提前停止/PGfalsePID0/tempDB0/其他base连接0/app高权false/保卷；原两轮和静态首patch错误未运行事实保留。B作者固定21:17:48→21:47:48窗口，受控process.title从node变为Next含嵌套括号标题后同socket lsof由正确PID变exit1/空，具体lsof内部实现未源码核查；修复后Linux ARM Mock8/23.755s和1057offline/85.34s，原首失败及准备错误另存，不抹去。

B修复在Linux通过/proc TCP/TCP6唯一当前UID/IPv4 loopback LISTEN/inode及同UID FD唯一holder证明PID；原Mac lsof路径保持。Mock还核当前UID、精确cwd、本次Playwright launcher亲缘和BUILD_ID，错误输入fail closed；真实read/write/items/native200继续已登记PID/build/source绑定。Python薄入口的ready/end查询使用项目固定Node调用同一只读helper，没有服务创建/终止能力或新通用infra。依赖准备只在独审自有环境按公开registry/frozen npm锁正常安装与build，无锁或生产权限变更，原授权内不新增permission流程。

**修复后Linux x64当前CI与真实全24尚未执行**。旧Mac24/native200/PG仅属于原a65观察路径，不能外推至新Linux查询；ARM成功也不代x64成功。下一精确四job CI必须实际证明默认read7/write10/items7、current checkout/head/build/13hash、完整标题集合、PG不变量及清理，以及首步23min/25min job/75s余量，没有延长、重置或缩集合。

## 正常集成与最终检查

在A已提交087上普通merge精确B849为 `53565290beafa16c73e4b0110a817c3dd8875b14` / tree `bb4033f06187a6997412bbe8e425df5399a2b074`，parents087+849，无冲突、不rebase/amend/force。A目标测试同087；B9code/UX/证据同849；backend/Graph/Worker/schema/migrations/API/预算/locks/原scripts/Compose同972。共享workflow原195行frontend job与原三个job逐字保持；薄入口CLI参数/window13hash/result schema及默认三stage/title7+10+7与现有workflow契合。A随后只改阶段导航与交接，不修改B实施或自有资源，不另建修复PR/管理体系。

本次一次完整 `scripts.check` 实际exit0：1057offline passed/337integration deselected/84.70s、两个既有lark-oapi弃用warnings；71Markdown0error、Ruff/268format/mypy193、frozen锁、Node24.21.0/npm工具链/frontend typecheck、Node及95Python锁包漏洞0，current/index/fullgit扫描0。另22-operation schema、无PYTHONPATH模块help exit0（零资源）、YAML/4 Bash/4 Python静态、default7+10+7标题集合、四点名artifact、diff check和source inheritance通过。最后文档数字收口另核docs和提交前三scope；不追加本地19/8/101/24/build、PG或browser。最终冻结source/tree及实际checkout/四CI由PR37冻结评论与Root验收receipt绑定，避免内部自指未来SHA；不编辑已正确的PR正文，不手动cancel/retry旧CI，维持Draft待最终裁决。

main仍 `59b350cb719a9d2fed3f68b1ee598fa0a9b97875`，A不合main/关Issue；Root当前四CI和最终继承增量核收后才正常main合并、同main CI及Issue33正式结案。D1=2026-10-10/D30=2026-11-08/300h、Phase3 A32+B18+Review10=60h、人工H/L not_reported保持；新provider/平台业务写0，无新视觉设计批次、用户Chrome/可见窗口/焦点/OS键鼠操作，飞书扩权/生产/Phase4及自然故障/p95/长期TTL等边界不变。
