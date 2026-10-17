# P4-A04 正式IM与窄SDK方法账本候选（离线，未放行平台）

parent为A03安全证据文档2f93f80935b9992aed2baf984302824776ebafab，业务前层a1cd/tree62230原36作者通过及Root独立Core36真实PG通过分别保留。本文只记录新功能候选，不把前层独审/PG继承为本层通过，不改C独占frontend/Generated或已冻结shared OAS/B三模块。

## 功能切片

正式BusinessMessage仅text/interactive二选一，UUIDv4原键必须传入；BusinessIMSDK复用同官方CreateMessageRequest与实际HTTP+code+原chat/message ACK规则。固定澄清委托同transport保原文本和原UUID；正式20SKU card由原frozen plan/hash/nonce renderer构建，固定result来自服务端terminal task/count/原Web origin，无模型生成。HTTP/业务错误/超时未知不换键或自动retry。

新0011 p4_im_deliveries伴随账本不升级原outbox禁发；原Card待ready、原身份/原会话chat+type/完整plan绑定，sender前持久sending/attempt1/owner/原UUID。发送前当前operator/identity/app/tenant/allowlist/原群/期限复核，原SDK ACK+message_id后同事务sent+不可变p4_card_bindings。unknown任何年龄停止自动重发；旧sending需WorkerSession旧OS死亡证明后新唯一Worker转unknown。真实feishu绑定默认拒绝，只有显式服务端live gate才接受该模式，Fake不能改成真模式。CLI仍未提供受控live入口。

终态result先仅为新Feishu conversation正式task生成唯一task/version original outbox+固定文本意图，T4/审批/items不回滚或复活；Web新周期的IM路由选择仍待明示，不自行继承某旧聊天。既有单Worker维护回调可注入IMStore，无新job、调度器或dispatcher；所有真实consumer/Factory装配另审。

SDKCallLedger接口只接方法名称及不打印参数的call closure。当前client实例窄proxy六方法：IMcreate、Base record create/list/update、同Base table/field list；不修改SDK/全局monkeypatch，不暴露contact/drive。原固定SDKWindow默认off/caps immutable；PG原window/caps/TTL/mode不可变，短事务预占方法cap，再当前scope/subject/org/shop匹配并调用一次≤10s/原绝对截止，异常/取消/PG未知不退预算。started为可能调用/预占，returned/raised/not_called分别保存；不当作HTTP wire或认证请求已完整计数。

账本只写HTTP/code、安全method/scope及business refs，不写request/option/body/URL/token/record/chat/open_id。Base/IM/clarification按各原intent scope协调；controlled_sdk Base或IM没有method ledger直接拒绝构造，Fake默认保持可测。SDK自动认证/刷新/重试的实际wire及bot窄读取尚需Factory显式预算与ledger，不能只计六pub method而宣完整真实调用。

## 证据与未验证

当前formalIM2/原IM7/ledgerproxy2/window6共17pure实际2.38s（后复验2.59s）通过，两旧SDK warnings；完整离线1319passed/88.13s、375integration deselected/mypy244/Ruff/334format通过，最后87MD0。新PG3仅collect（单Worker卡→binding→T3→result、unknown无重发、原SDK窗口cap不复位/immutablecall），尚未执行，0011迁移/runtime grants/实际回执都待Root独审后下一固定owned窗口。首type/format修订为作者检查，不隐藏或拿pure替PG。

原a1cd的feishu_delivery_read.py worker_ready=None多4空格确使C2全check在format exit1，后续mypy/offline/npmci/audit not_run保持；A单owner用原Ruff修正一行，无业务语义变化，当前334format0，不忽略检查。C2新37contract/12UI由Root另核，当前A共享CI使用既有config完整自动collection、没有硬编码8或筛选；合最新C后执行原全12，不能拿memory测试签真实平台或整check。Root下一普通merge协调，C不写此A文件。

新IM sync投影及实际SDK事件对C读接线必须协调后从最终冻结源同步；本候选未改shared OAS，不并写C。SDK/正式Factory/长连接gateway/preflight尚未ready，平台/provider0，旧secret/env/DB未读；用户新15列表虽已有，当前schema/type/app资源仍需最短已授bot/同Base窄读取。tenant/group/A/B/C不足API权时historical_confirmed/not_run，真实当前消息/callback+PG权限逐项current_observed，不加scope/发现框架/P1重复采样。

原AC08/M1的cleanCompose薄m1-offline-demo排在本IM/Factory功能批后：复用P3 API/单Worker/Graph/原twenty+known70/Next；mock/model not_used/simulated_web/controlledFake/senderfalse，不读Feishu或模型私配/不发平台。仅API/frontend回环临时端口、PG无hostport、own600seed/卷保留及同ID重启证据，source/独审/实际freshCompose另核，不拿test Preview签AC08。日期/50h/原300h/人工H-L not_reported及全部边界保持。
