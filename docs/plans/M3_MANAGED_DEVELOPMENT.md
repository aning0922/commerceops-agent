# M3 托管开发与交付记录

## 当前事实

- 授权日期：2026-11-03（台北）。主控会话：01a19f1b-f4c0-75c1-a9f0-8f8b88db72d5。
- 远端 main 只读核对：6d3a8f7bf3d36c6c1dcfd5072a3297be4cc88265；Issue49 closed/completed。
- 状态：STARTED / CONTRACT_PREPARATION；主体功能、测试、CI、部署均未在本阶段验收。
- 当前目录 README 分支 e06b665 保持原样；本阶段使用独立 control/backend/web 工作树。

## 交付顺序

1. 日报确定性指标与异常规则，冻结数据口径、快照来源及验收金标。
2. 复用单 Worker / PG jobs / outbox 的持久调度、去重、补最近一期及受控推送。
3. 报告绑定的证据追问与最小可用 UI。
4. 白名单动态只读工具及实际工具序列/权限/预算评测。
5. 版本化 SOP 检索、可定位引用、人工审核及幂等保存内部草稿。
6. 必要本地/PG/Web/真实模型或平台证据、独立审查、精确 CI 与主控核收。

原范围依据：PRD、AGENT_DESIGN、ROADMAP、30_DAY_EXECUTION；日期与工时均须按新实际记录，不能把历史计划余额当可用额度。缺少许可资料、模型预算、接收对象和真人操作时，相关真实 Gate 保持 NOT_RUN，离线候选不代替正式完成。

## 分工

- Root：本文件、阶段授权导航、集成工作树、任务依赖、模型调整、必要发布与最终核收。
- Backend：合同草案、确定性指标、持久化/API/Worker/共享 DTO 及相应测试；不改 frontend。
- Web：仅 frontend 与最小 UI 实施说明；消费冻结且已提交的共享合同，不虚构接口。
- Reviewer：先只读评审合同与范围，再评审精确实现提交；不接管作者源码。

各开发者不得修改 Root 的阶段导航、另一开发者文件或 Harness 资产。共享 schema/迁移、根配置和 CI 只由 Backend 提案并经 Root 协调；锁文件或 workflow 必须有实际必要性。Root 普通合入精确已审提交，不 reset/amend/force，不读他人未提交 WIP 作为交付。

## 模型调度

初始：Backend Sol/high，Web Terra/high，Reviewer Sol/xhigh。常规文档/机械接线可降为 medium；跨层恢复、权限或并发阻断可提高强度，必要时以独立专项使用 Astra。工具实际接受的设置与回执为准，额度不可用不自动转付费 API。

## 外部边界与验收

新开发授权不复活旧真人/SDK/Native/CI一次性窗口，不修改旧 once 或 UNKNOWN。真实外发须绑定已授权对象；当前没有新增 paid API 或业务凭据访问。开发者无 push/PR/Hosted/main 权限，统一由 Root 在具体可审交付就绪后处理。保留现有所有安全、业务、恢复、权限和全量 CI 要求。

## 证据账

本次启动仅核对 GitHub main 与 Issue 状态、创建工作树及本文件；未运行业务测试、模型评测或服务。后续按实际 source SHA、命令、退出码、资源与限制增记，不预写通过或完成。
