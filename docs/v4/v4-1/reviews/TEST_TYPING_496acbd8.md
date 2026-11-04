# V41 工程门槛两测试typing窄修独审

日期：2026-11-04（台北）。source `496acbd8e2c8f172a2bba5724857d67abfab77bc`，tree `c8d8b498c225901b279e1fd6b5928c52a71a5d58`，parent `e466f03436ba726b6050b10e879da68d80c7e372`。仅tests/v41/backend/test_native_parse.py与test_http_boundary.py，39新增/17删除。

结论：ACCEPT_EXACT_TEST_TYPING_PATCH，未见P1/P2。可由Root冻结为后续新engineering/FullPG候选；本回执不授权或代签完整重跑，不变更独立e466浏览器案的source身份。

Native events显式为list[int | dict[str, object]]，stop/proofs为实际字典形状；proof与pid以isinstance守卫收窄后仍对同一原proof PID执行os.kill(pid,0)并要求ProcessLookupError。新增TypeError只加强错误形状拒绝，没有cast、ignore、Any替代或跳过真实reap断言。HTTP calls改为tuple[object,...]，三个stub返回dict[str,Any]与原BusinessStore返回契约相符；stub仍原样raise并记录调用。七个测试参数注明实际tuple[TestClient,BoundaryStore]，origin/value/suffix对应原parametrize取值，未修改fixture创建或用例选择。

独立AST核原22个assert完全相同（Native8/HTTP14），全部decorators/markers相同，无type_ignore；精确diff确认无生产、前端、native helper、依赖、skip/xfail或参数矩阵变化。精确archive目标mypy两文件（follow-imports=silent、no-incremental）native0，Ruff check0、format --check0。未运行任何pytest/纯child/reap、PG、服务、浏览器、Full/CI或远端操作；作者21PASS/9.82s仅保留作者证据，不冒独立复跑。

Root报告原e466工程首轮145.723s因mypy18错误中断的原结果/seals保持；新typing检查通过不追溯重签旧工程失败，也不签新完整工程或FullPG已通过。后续真实运行按Root新精确source/窗口单独核验。
