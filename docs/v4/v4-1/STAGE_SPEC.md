# V4-1 本地托管阶段

用户于 2026-11-04（台北）授权继续托管至上一轮指定的下一阶段完成。本阶段按原任务包完整六卡 V41-01—V41-06 交付；上轮摘要只列前三项，不能用该摘要削减整个 V4-1 Gate。业务起点为已核 V4-0 `1730194028a01ddea0bbc573774d740ea4a29d55`，原 V4-0、M3、Harness 及原工作树保持原样。

## 阶段成果

1. V41-01：14 模块导航与 Next.js Shell、主题、状态和错误组件；未开放类别明确状态，不计为已完成业务页。
2. V41-02：经营 KPI 和统一查询／钻取，同一来源、店铺时区、币种、期间与快照；金额 Decimal，未知成本不生成毛利，跨币种不合计。
3. V41-03：经营首页、图表、规则洞察、异常待办和全局 Copilot 容器。真实数据来自新本地 API；模型调用未启用，规则计算不冒充模型回答。
4. V41-04：商品／订单授权列表和详情、受控演示覆盖层、商品标签与订单履约接口；外部 Woo 零写。
5. V41-05：商品／订单管理 UI、详情关联、编辑、筛选分页和安全导出；跨店／身份切换及过期立即清敏感状态。
6. V41-06：CSV／XLSX 预览、字段映射、质量回执和原子确认导入；导入后 SKU 可查询，恶意／超限输入拒绝，错误无部分提交。

## 权限、事务与事实边界

沿用已批准四份合同和 V4-0 真实身份／双店隔离、绝对 TTL、CSRF／Origin、generation／epoch、原键／UNKNOWN 和当前授权核验。前端角色选择不授予权限，受限管理员没有默认业务权限。业务编辑只在当前演示租户覆盖层；同一请求键只一次效果，当前权限在提交前重新核对。reset 与业务写必须同锁序线性化，不让旧写进入新 epoch。所有数据、汇总、详情和导出共用同一事实源。旧 M3 单 Worker／Graph／真实外部协议保持，V4-1 不投递新外部任务。

原型 HTML／ZIP 是视觉和交互参考，不是业务权威，不内嵌成最终应用。历史 A 文档中的 PROPOSED 和 V4-0 NOT_STARTED 保留原日期；本阶段增量接口由 API owner 给精确设计，Root 冻结且 Reviewer 专项核对后实施，不修改原四份冻结文档。

## 单 owner 和集成

- ROOT：阶段范围、增量合同、路径／依赖、Gate 与普通集成提交；`docs/v4/v4-1/**`、`docs/v4/acceptance/v4-1/**`、必要状态索引。各 proposal 文档由对应 owner 独占。
- API：`backend/src/commerceops/application/v41/**`、`infrastructure/v41_*.py`、`entrypoints/v41_*.py`、唯一共享 `entrypoints/api.py`、新 0025 迁移、`tests/v41/backend/**`（下列GC专门路径除外）。V4-0 共享身份／seed/reset 接点须先合同列明；旧 current-head PG 期望仅在新迁移明确后窄释放，历史迁移段不改。
- WEB：`frontend/app/v4/**`、`components/v4/**`、`lib/v41-*`、`frontend/v41-tests/**`。生成 schema 从已审后端来源生成，旧根布局／锁／业务客户端不并行改。
- GC 测试：`tests/v41/backend/test_gc_pg.py`、`tests/v41/backend/gc_fixture.py` 与 `proposals/GC_FIXTURE_PLAN.md` 单独由 GC owner 控制，API/QA 不并行编辑；只在新 owned fixture 测试，恢复和自然时间证据分账。
- QA：`tests/e2e/v41/**`、`frontend/v41-e2e/**`、本阶段真实 API／PG／浏览器回执，不代写业务、共享 schema 或迁移。
- GATES：工程工具／扫描和动态 Full PG 计划、私有执行包装器；共享正式脚本先由 Root 指定唯一 owner，不改原扫描规则或历史例外。
- REVIEW：独立提交检查、权限／事务／导入专项和精确 SHA 核收；不代作者改 WIP。

每个可审切片自检成功后普通 commit；原生预检在提交之前完成。任何错误立即停止该命令序列，不在失败后继续提交；相同未知失败先定位，历史失败／UNKNOWN／原请求身份保留，不自动重放。已核切片正常 merge；单文件文档或隔离最小修复可由 Root 对独审冻结 commit 作普通 cherry-pick，保留原 refs／原 SHA 与组合映射，避免带入未审祖先。无 reset／amend／强推或删除原失败 refs。

## 阶段 Gate

Fast／专项检查先跑受影响路径；迁移／权限／共享 API 完成后运行当前精确动态 Full PG 双线、原严格配对和 G1 三／G2 六；完整工程检查、真实 API／PG／Web 及桌面移动浏览器按实际 source 分账，不把旧 745 或 4316 数量预填为新 Gate。验证过滤分页／同源指标／标签读回／订单商品关联／导入后 SKU 查询，跨租户店铺／过期撤权／旧版本／并发同键／重置竞争、导入恶意超限／事务回滚与恢复。

界面覆盖 1440／1280／390、原生 200%、菜单／焦点／Esc、reduced-motion 和迟到／隐藏／断网清屏。原 M3 与 V4-0 对应安全和业务 Gate 不降低。所有未跑 Full／Hosted 明确记录 NOT_RUN。单次实际资源只用新 owned 项目、库、配置、端口和 CIDR，提前固定源／UTC／清理预留；原资源／私配／服务不启动、不复制。

## 结束边界

完成 V4-1 本地 Gate 后交付可复现入口、操作步骤、截图、卡片完成表、实际 SHA／检查／耗时、失败和清理。V4-2 不自动开始。Hosted CI、PR／main、真实模型／embedding、飞书／Woo 外发与生产发布未授权；依赖的公开工程审计按原流程分层，不称完全零网络。模型按 Sol／Terra／Astra 与任务复杂度调整，实际费用不可见记 UNKNOWN，无付费 fallback。

用户随后新增授权 Root 及时常规推送已审集成切片，规则见 [推送合同](PUSH_POLICY.md)。此补充只覆盖阶段分支 push；PR/main、Hosted、真实外部业务与生产继续未授权。
