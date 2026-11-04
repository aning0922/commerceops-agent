# QA与WEB最终事实文档候选独审

日期：2026-11-04（Asia/Taipei）。**结论：ACCEPT_SOURCE_SPECIFIC_EVIDENCE_DOCS，0 P1 / 0 P2。** QA candidate `61b6e78a0bf195e9659c3cb22845af78b3888849` / tree `63be060bc722b99f66e9bc26420875112dfef1b3`，parent `d18df5a11573a45bf7232d15eaa7d8107bbba3ea`；WEB candidate `d991d7f7fe2d07a905340de5c7e1b7873a6ee201` / tree `8cd2f383a75489bf58d7d5d0933e947fd896d6b4`，parent `f7e6a67e7ce78e972643a36f442ed0cd7c9b296b`。仅核已提交文档，不读作者WIP、不重跑服务。

QA恰15个新增文档：说明、矩阵、11份HTTP安全回执、legacy24与N01six。与独立实际证据核收 `294903a4e290df3e95ce6c0fe7a2452febd963e3` 交叉核对，并独立验证62个去重原件路径SHA256。11个矩阵链接及receipt_sha256均匹配提交对象；每份source/tree/project/database/image/start/deadline与原case一致，close/native/cleanup与原外层和安全批回执一致，PG白名单字段计数与原final_pg相同。没有复制身份/操作标识、私钥或私有异常正文。

F1两项/R2五项/R3四项明确分记，没有“11项同R3实跑”的表述。最终tenant行数与active count分离；仅capacity/bootstrap_restart以原实际容量断言支持active3，其余未单独采集保持UNKNOWN说明。所有旧失败及各自NOT_CAPTURED原因边界保留。说明中的新namespace/DB/卷可由各case登记核对；本次未读取私配内容或原操作键，未将其明文拷入文档。

Legacy三report的24条、N01六条测试记录（含状态/位置/时长）与原JSON逐对象相等，source模式与mock-fixture口径保持。两parent native均明确NOT_CAPTURED，不从test_exit推造parent0；custom reporter没有retry count，文档也保留NOT_CAPTURED。N01原停止-15/143未改写为全0，旧Web parent路径失败另留原件hash。M3三flow live明确NOT_RUN。

WEB唯一新增UI_ACCEPTANCE.md：三实际路由进入同一演示组件，与当前catch-all入口一致；不称三套业务模块或66页完成。文件清单与已核实现相符。UI_FIXTURE_363_FULL的35/0skip/0unexpected/0flaky只属于合成响应来源；独立核其stats、receipt、visual-metrics与原 `.audit/v4-0/ui-fixture-363-full` 三原件完全一致，不转作真实API/PG结果。

R3单个固定真实browser、390及原生200分段证据的表述与本轮原件一致；没有把35fixture当成35实际browser。九个用户验收项均未勾选，真实断网/网络恢复矩阵、用户设备、完整无障碍/人工业务理解仍待单独验收。V4-1标PLANNED/NOT_STARTED，Shell与经营KPI边界符合冻结TASK_PLAN/PRODUCT_GAP_AUDIT，六规划链不冒充已交付，不启动后续阶段。

该文档接受不表示当前ROOT工程全检、PG双线、发布或真人已通过。新增文档仍须进入ROOT实际后续工程检查；原件绝对路径是本机定位，不是可移植交付附件。无需改作者正文，按各精确commit普通整合后保留独立回执即可。
