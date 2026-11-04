# V41 必需运行见证与失败判据

准备已按Root7f1667a/后端55ce及c696、743、55ce三份审查校准；全部尚未运行，不能作
Gate回执。runtime_definition仍保留772历史快照与HOLD，须等DDL修正、最终CLI/精确源
重新核准后才可变更；本清单不更新这些启动输入。S04是私有invocation准入能力，正确私有
lease授权的可信监督器不是无能力攻击者。runtime_definition仍HOLD，
不存在可启动runtime_handoff。仅Root未来新owned对象/UTC可放行；不使用旧DB/凭据/进程。

| 场景 | 必需实际见证 | FAIL或UNKNOWN条件 |
| --- | --- | --- |
| 低权binding组合攻击 | 实际current_user=commerceops_app；合法当前operator的正向业务路径；尝试改自己bound web_sessions.csrf_digest，再自选binding/lease/process调reserve与未bind forged stop；原始SQLSTATE与事务末态 | 旧锚可写仅记信息；格式合法双段伪binding仍可reserve即FAIL，随后原利用链的伪stop也保留。非分类SQL错误不是拒绝通过。探针最终必须实际ROLLBACK恢复原锚/六表。 |
| 已bind、子进程仍活的伪stop | 可信最终fixture真实Popen child并COMMIT PID绑定；/proc存活身份与birth；另一路真实低权调用仅获job/process/PID等公开行字段，不获正确lease，使用空/错误lease及伪proof；读回同job/PID/slot | 无正确lease的伪stop被接受、slot变化、真实进程未存活或角色错误均不可通过；不得把可信fixture正确lease交给攻击者后声称SQL应识别其谎言。fixture必须先证明正向身份/容量条件，避免“本来无权限/已满”伪装安全拒绝。 |
| 父进程实际消失 | reserve COMMIT、bind COMMIT、同process_ref与实际child在父死亡瞬间存活；既有候选os._exit(17)与另行SIGKILL(-9/137)分别记原生模式，独立DB UTC快照 | 只杀Docker CLI、只模拟异常或直接写DB状态均无效；受控exit17不冒称SIGKILL。父死亡无可信wait，原slot必须保持占用；DB可保持RESERVED/RUNNING/UNKNOWN，业务只读lookup必须UNKNOWN，不能要求伪造字面parse_state=UNKNOWN。 |
| 父亡后容量与清理 | child独立alarm/实际退出单记；原row/slot仍在；同tenant新准入在明确未来窗口内实际拒绝；保留新卷 | child到期/PID消失不等于原parent已wait；任何expiry/GC/重试自动释放slot即FAIL。不能SQL改STOPPED或删除job。清理停止owned服务并保卷，不抹原UNKNOWN。 |
| 真实reap后释放 | 最终run_parser实际Popen handle communicate/wait/native；同父kernel wait事实；随后原stop事务COMMIT0、同job STOPPED/slot NULL；新准入另记 | 只有布尔reaped=true、stop_proof自洽摘要、异常捕获或cancel不构成见证；stop事务失败仍占槽且不自动重试。先放槽后wait即FAIL。 |
| 撤权后可信reap | 实际child运行中；owner通过最终受支持撤权入口COMMIT；同父真实wait后窄cleanup stop可提交；publish/confirm仍重核拒绝且零业务增量 | 以撤权为由留下实际活进程、用stop权限扩大publish权限、失败回执当成功、无receipt/event/import零增量末态，均不可通过。具体fixture/角色权限必须等S04最终设计，当前未猜新角色名。 |
| S02撤权交错 | 真实PG屏障证明principal/credential锁先后；原写与原撤权native结果/COMMIT各自保留；DB与HTTP末态 | deadlock 40P01、lock timeout 55P03、statement timeout 57014、503、撤权回滚或原操作自动重试都不能当正常撤权完成。写先提交可保留原效果；撤权先线性化后写不得提交，后续旧身份不得读写。 |
| apply后强制回滚 | 实际app角色固定v41_apply_action返回；同事务1effect/1receipt/1event；SET CONSTRAINTS ALL IMMEDIATE完成；主动抛出后实际rollback；新事务原scope六表/私有binding锚/fixture库存金额摘要与前值相等 | 未到apply+约束阶段、仅回滚空事务、schema/count假字典、缺新事务读回、原key已有提交或HTTP原key不为UNKNOWN，均不可通过。当前只准备标签固定操作，不能代签“导入中途插行失败”的独立故障场景。 |

sql_probes.py已经接固定真实app-role SQL组合攻击/标签apply后rollback，transaction_recipes
在catalog入口先登记原key和新私有输入，再通过同固定daemon的compose exec -T v4-api执行；
每个native/start/end/input hash/log hash独立保存。UNKNOWN不重发，不用假HTTP响应；结束后真实
HTTP GET两个原key应UNKNOWN，再将SQL_ROLLBACK_VERIFIED追加到原观察历史。父亡、活child伪stop、
可信reap/撤权屏障仍需最终API owner fixture，并保持NOT_RUN；组合攻击通过也仅标PARTIAL_S04。

终态subjects由全部writers/API/oneoff退出后、PG停止前的只读观察器核验；旧tag版本的receipt/
event保留，当前效果行可归后续版本，禁止用聚合行数或schema final替代逐原key/版本关联。
