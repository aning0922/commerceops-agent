# 4fec工程r3实际回执独审

2026-11-04（台北）。结论：`ENGINEERING_RUN_ACCEPTED_FOR_4FEC_ONLY`。source `4fec4a7416d7b9434d979f461d5da78508cfb850`，tree `20044a26fe39850cc31943bf4e328abba3936f3e`；实际树为commerceops-v41-engineering-final-r3，case `.audit/v4-1/engineering-4fec-r3`。只接受本次完整scripts.check工程运行，不签PG、browser、Native、后续harness delta或阶段完成。

独立核owner seal原始SHA-256 `c9f9e7218238fd86cec52e4e3fdd844bb5e48e4a45e5fccd3ff9f0454cd6486b`；checks、outer receipt、outer log、probe log、registration五项原始字节摘要与seal一致，也与outer已有索引一致。probe日志摘要为 `c084fb76c64849368ffa6542edb4f568bc14bc45c31dbd1557ee811a46e009eb`。没有读取netrc、环境文件或key材料。

实际命令为本树Python `-m scripts.check`，UTC 07:01:34.918236至07:27:04.485508，差值独立算得1529.567272秒。checks记录command native0、timeout=false；outer记录worker native0、parent_timeout=false、parent_failure=false、notes空，seal记录outer native0。原argv采用已审87工程wrapper，窗口07:01–07:51Z、reserve300；未借用PG wrapper或PG预算。source-before/after的HEAD/tree/clean状态与tracked摘要完全相同。

精确4fec源码定义的13个顺序子命令及最后Python审计共14个CHECK标记，与实际日志逐项同序、无缺项。源码对任一子命令非零立即退出；uv export仍按frozen/all-groups/no-emit-project执行并检查返回，再以require-hashes/disable-pip/strict执行pip-audit、拒绝vulns或skip_reason，最后才输出完整结束标记。export本身没有独立日志标记，本次从精确源码控制流及后续完整完成证据确认经过，不补造独立native记录。

实际结果：锁检查完成；Markdown312/errors0；Ruff通过、932文件格式已符合；mypy616；npm ci ignore-scripts完成，Node24.21.0工具链验证通过；Copy Ajv24 cases/5 operations strict；M3 no-server为10文件、collected=executed=46、skip0/retry0，源码同时核完整收集与实际执行相等。offline实际5377 collected、776 deselected、4601 passed、0 failed、4 warnings、1346.64秒，排除节点不冒通过；四warning为依赖废弃API/事件循环及原多线程fork告警，保持原记录。前端tsc完成，npm audit零漏洞；直接读本次python.json得95依赖、vulns0、skip_reason0，与日志相符。

敏感扫描单列：dir/index各findings0/native0；history原生native1，包装层exit0，1760条全部已审分类、blocking0。独立统计日志分类为153 reviewed_public_false_positive和1607 reviewed_public_merge_copy；这里核实际日志分类账，不重新执行扫描或重审1760条批准来源。refs_before/after作为information确有变化，不宣称所有refs冻结不动，也不将本次历史扫描结果套用后续新增refs。

实际Root binding原始摘要 `9ec738e82b944ded3af45da58a5c405bede0637ce0754d5d6fe142a8d12548e2` 与outer argv一致，完整内容等于checks中的source_tool_lock_binding。14文件指纹逐一独立对精确4fec Git blob匹配；记录的4 runtime为Python3.12.13/uv0.11.25/Node24.21.0/gitleaks8.30.1，3 binary摘要为uv/Node/gitleaks。cleanup记录probe0、groups_stopped=true；outer绑定worker33377/parent33374并记录正常退出，无额外notes。

补充原件：prep receipt摘要 `d48792c255e0effdc8bf08ddf63df279103655fc50ff6296f60ea90e6554a594`，UTC06:58:32.418397至06:58:33.311776；launch receipt摘要 `9ab6b3f6efb267258f3cf765a7943d36e16344dc467104fb996f2c71add72a06`，UTC07:01:34.141698启动。两者identity与worker完整14/4/3记录相同，五项pins前置记录相同，launch argv加--worker精确等于outer argv，launch native0直接支持最外层退出。prep记录新Git外HOME/TMP的0700/UID、Git128且stdout空，launch再次记录Git128；没有把旧e7准备证据换名。prep的216个source_digests与精确4fec全部216个包Python文件逐项独立比对相等，安装字节相等由prep及launch原件记录，未事后重复导入或核安装目录。

owner seal另报告33374/33377不存在、source_tool_identity_after_equal、wrapper_dependencies_after_equal和package216_after_equal。Root/owner明确当时已计算并断言，但没有保存独立after map或停后ps stdout/stderr/returncode；这些仅作为owner封存声明，不冒逐包/逐进程原件核验。已注册组的probe0/groups_stopped、worker0/无timeout/notes空及真实source双快照是直接控制流原件，足以核本工程命令完成与已注册组收口；未把ps原件缺失扩大为全部系统资源独立清理已证。本次没有重跑工具、ps、网络、扫描、PG、browser或任何工程检查；旧工程失败及其原始trace不因r3成功删除或改写，后续组合必须另记。
