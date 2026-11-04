# V41 S01/D01 父路径独立审查

日期：2026-11-04（台北）。source `187e26cb181c4247fe26364fd68fd6e106d5a9ad`，tree `77bd0eaf4bbe5db85e72072f071cd7f1bbea093c`，parent `ca69b83404c4270bfd9cef09a58a343c148769fb`。只读精确增量、Root590后端和明确依赖WEB `830b97c5b52558a2f6f49f4bd0afb1406da3481d` 两business文件；未读WIP、不运行资源。

结论：HOLD_BROWSER_GROUP_CLEANUP，一项P2阻断父路径停止证明；其余下述源码接线可保留。H02 ca69的独立接受回执不受此项影响。

P2 S01：`browser_shell.py:264-313` 仅从带本案user-data-dir参数的行重新发现leader，TERM后若leader退出、同一已核PGID仍有不带该参数的子进程，inventory会将其过滤为零；stop_residuals因此跳过KILL并返回remaining=[]。`owned_driver.py:520-525` 据此仍可令writers_stopped为true并导入journal/继续末态采集。若首次残留检查时leader已退出，单独遗留的此类组成员同样不可见，可能直接返回clean_exit=true。已核锁定Playwright本地launcher在非Windows以detached=true创建独立浏览器组，原Supervisor对Node probe组的核验不能替代此组的消失证明。

独立脚本化清单反例：开始为已核profile/binary/UID的leader12345及同组renderer12346；模拟TERM后仅保留12346，未启动任何真实进程。实际候选函数只记录一个SIGTERM调用，返回forced=[12345]、remaining=[]、clean_exit=false，尽管模拟ps仍明确报告存活组成员12346。强停事实确实会使该案失败，但remaining误判仍允许过早采集，且无法覆盖首次检查前已失去leader的分支。建议在启动/存活时保存经核实的浏览器PID/PGID身份，清理以完整已归属组的独立无存活证明结束；leader或profile字符串消失不能当作组已空。无法核明归属时保持UNKNOWN/HOLD，不采用系统浏览器PID或放宽信号对象；补leader退出/同组子进程仍活的组件负例。该发现是源码/模型反例，不声称已发生真实浏览器泄漏。

非阻断事实校正：`runtime_subjects.json:286-295` 的historical_definition_gap.source写05d2086却记qa_map_entries=12/四缺项；05d已是16项。应绑定其95deb父版本或原盘点精确源，保持历史事实而不是把缺口归给已经修复的提交。

已核可保留：

- shell_navigation在Docker前核固定八条已提交浏览器来源和Root私有runtime binding（source/tree/auth ID/case/UID/project/image、canonical可执行路径/hash），终态再核原件与binary。固定双spec/双title、单worker、无retry/only，报告须恰好2expected、0unexpected/flaky/skipped及每项唯一native passed结果；只有进程native0不通过。Shell三PNG固定路径/hash和safe receipt绑定source；native200明确NOT_RUN。
- main固定启动模块，无任意spec/命令输入；新HOME/TMPDIR、禁下载、固定executable。735四owner文件逐字节未变，不恢复903 CLI。WEB依赖是另一个精确提交，QA本片未带入或编辑它；实际组合仍须Root冻结。
- journal仅在writers被判停止后导入，严格字段/source/UUID/计数、完整换行、每key先意图后ACK、Shell无业务写，行错误保留原件并记录失败，已验证有效意图不会因后行损坏丢弃。subjects新增请求数组有界并兼容原无请求的HTTP记录；未将UNKNOWN改成重发。
- request_witness先复核本地body hash，再按真实DTO补默认值/规范化。动作method/path/body与Root590 Store.action canonical结构一致；preview使用去file_base64的规范命令和实际解码文件digest，与Store.preview一致。最终实际DB canonical与原意图语义对照，服务端receipt/event/effect hash和身份校验保持；ACK_COMMITTED无DB回执现明确失败，原本地hash不冒服务端payload_digest。
- WEB830透传fixture确实await writer.operation后才route.continue，失败abort；创建返回scope也先登记再交UI。此仅核接缝，不代签整份WEB实际UI或延迟响应清屏矩阵。Shell普通logout断言不冒迟到成功响应专项。

独立验证：精确187 QA archive加已审Root590 backend源码作明确依赖，运行test_browser_shell、test_subjects、test_final_facts、test_owned_driver共32 passed，2.43s，nativeexit0。清理反例使用mock ps/killpg，nativeexit0，无真实信号。没有运行作者全134、type43或TS；没有浏览器/HTTP/SQL/owner/Docker/服务/Full/CI/远端写入，真实凭据未读。native200及logout后迟到成功响应仍分别待独立路线和实现，不扩大此审查为全部浏览器验收。
