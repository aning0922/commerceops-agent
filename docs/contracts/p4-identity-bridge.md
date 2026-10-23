# P4 飞书与 Web 身份桥（首批实现与跨入口作者定向实测）

用户/Root规定各入口使用同一现有principal与组织店铺权限；不增加SSO或客户端身份选择。正式Feishu身份是`provider='feishu'`和`(app_id,tenant_key,external_subject=open_id)`，Web身份是既有`provider='web'`及受信credential/session。两条identity必须由受控PG配置指向同一个principal，平台回调不得提交或覆盖principal_id。创建新的平台identity不自动创建另一业务principal，也不自动赋权。

## 当前服务端连接

`FeishuBusinessStore.actor`在PG按可信SDK平台身份取得principal/organization/identity/auth_version。T1/T3调用原P3同事务服务；FeishuActor分支校验当前身份映射/enabled/auth_version，不创建Web session。WebActor仍由原Cookie/session解析，保持原登录/CSRF/Origin流程。单个principal可以同时拥有两种identity，`lock_p3_permission`保留原Webcredential条件并增量加入明确组织应用租户匹配的Feishu条件，仍检查同一当前role/shop grant。

Feishu-created任务的requester_id就是共用principal，conversation.channel='feishu'且聊天/话题隔离。原Web可见规则保持：operator只本人且同授权shop；approver必须currentgrant及该审批eligible；admin只ops，兼任其他角色另算。深链只传原task/approval/item稳定内部ID，重新过服务端授权，不含nonce/外部resource/幂等token。已有决定不因入口不同重新执行，当前auth_version撤销会同时影响Feishu callback及Web session；旧身份重映射不得回读原入站回执。

## 首批与必须补齐的实际证据

首19PG由`initialize_p3`预置一个principal的Webidentity/credential/session，再新增同principal的Feishuidentity，验证正式T1/T3/PG当前权限；随后2真实PG/API/11.70s已验证同principal Web读取/原Feishu决定与同语义重复、principal撤销双方拒绝；参见PHASE4_A01，独立审核/精确CI另核。其他角色/店铺增量仍沿既有规则及后续M1必要矩阵：

1. Feishu-created task由对应已授权Web session读取，Weboperator请求者/approver eligible规则不变；另一operator/跨店/admin-only拒绝。
2. 相同principal通过Feishu批准后Web读取原decision_source='feishu'和原决定，无第二执行/审计/resume；Web-first决定的Feishu相反动作冲突。
3. 撤销principal/role/shop grant后Feishu当前动作与原Web session一致拒绝；重新登录不越过当前权限，不能伪session。
4. 全部响应符合受审共享Web读取schema，业务Mock、approval来源/模式、平台delivery分别记录；本批没有human_feishu/平台sent证据。

当前跨入口作者定向2通过，源独审/精确CI及正式M1仍待；首合同49pure及独审不代替主体Gate。真实身份资源当前needs_reverify，Root审后有限窗口才允许核实，不读旧secret/env/DB或假定历史A/B/C配置有效。
