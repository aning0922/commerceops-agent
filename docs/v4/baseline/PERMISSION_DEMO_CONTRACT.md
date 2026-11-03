> 状态：PROPOSED / A阶段候选合同；V4-0代码NOT_STARTED。冻结的是文档内容，须用户审核并另发B授权后才允许实施。绑定远端M3 `952e6246deb01ec763f2541d9f316753987744f3`；不修改旧业务合同。

# permission + demo · v4-v1 候选

## 已存在 already_existing

SessionStore以PG token_hash查session，当前credential/identity/principal/auth_version核验；actor_guard复核会话有效期与主体映射，role_scope调用business.lock_p3_permission。/api/v1 middleware做当前身份、路径能力、POST Origin/CSRF；cookie commerceops_session。详见 reviews/M3_BACKEND_AUDIT.md。本合同不放宽该路径，不给admin隐含业务权限。

## V4隔离认证 proposed

V4端点新增专属boundary，因现有middleware只匹配/api/v1，不能以挂载/api/v4即受保护。独立opaque cookie建议commerceops_v4_demo，Path=/api/v4、HttpOnly、SameSite=Lax、HTTPS下Secure，不复用或覆盖原commerceops_session。仅新owned loopback开发可按显式local_http模式测试，公网必须TLS；不放宽现有配置。所有响应no-store/Vary Cookie, Origin。

Dedicated V4 resolver读取demo token并核DemoSession租户/epoch/到期/撤权、绑定旧WebSession，复用既有credential/identity/principal校验语义、actor_guard和shop权限原语（公开demo bearer不进入旧SessionStore.authenticate）。若既有credential映射约束需要适配，仅唯一SCHEMA/API owner新增窄demo登记入口；不能增加通用免密码企业登录、不能给客户端role字段赋权。精确存储/函数需实现前专项审查，与旧M3行为不兼容则HOLD，禁止绕过旧guard。

进入演示：GET bootstrap仅分配短期匿名nonce/CSRF；POST session经Origin+CSRF+速率/并发限制，在PG原子登记服务器tenant/principals/双店授权和session。首次进入默认operator，无demo/demo1234。30分钟绝对TTL，不滑动延长；到期须明确重新开始新空间，不能自动创建来掩盖UNKNOWN。并发候选上限3个活跃租户，开发验证容量含5个访客请求：额外访客429/Retry-After，不随机踢出。此为待批准参数，不是已测容量。

## persona、reset与防旧请求

三个persona是同一demo tenant内明确不同principal。服务端只接受persona_id意图，按当前会话+预登记allowlist选择目标，重新核全部identity/grants；不接收principal_id/role/tenant_id/auth_version授权事实。切换原子更新current binding、auth_generation和CSRF nonce，保留30min原截止，不提权真实账号。业务请求携带expected_generation/epoch作CAS，不可用于决定身份。旧generation/旧CSRF拒绝，当前账号店铺范围仍需查DB。

Reset只对当前tenant，先锁tenant/session并检查CSRF、epoch、当前能力，事务推进epoch/generation并更新当前session绑定。浏览器可保留opaque session定位，但旧epoch/旧身份及CSRF立即无效；旧授权不是因cookie还在就有效。成功后清敏感缓存、取消请求，GET current获取服务端新generation、persona和新CSRF。采用不在响应丢失时必须重发cookie的控制设计；若最终实现选择轮换token，必须先解决丢ACK后的受限只读恢复且独审，否则不得实施。

所有控制写入（persona/reset/logout）按同一稳定会话owner+operation+request_key存receipt，摘要包含原epoch/generation与payload；业务写还绑定principal/shop。操作原子写receipt与效果。ACK丢失保留原key，只允许当前有效session读自己的安全控制回执和GET current，不重复POST。先查已提交receipt可返回最小结果，不携带旧persona业务数据；若无receipt仍UNKNOWN，不将404视为回滚。新的业务写必须持新的CSRF/epoch。logout完成立即撤销会话，清cookie；若丢ACK可用GET current的401显示未登录，但不能据此伪造原logout COMMITTED回执。到期/撤权后无只读业务恢复例外。

## 操作权限（proposed新能力名，不假称现存scope）

运营：当前有grant店铺的读取/内部草稿；禁止审批。审批人：当前被指定且有grant对象决定；除兼任运营外不建草稿。受限管理员：演示配置，仍无默认业务读/审批。任何persona可通过演示控制界面重置自己的tenant/退出，但不可改外部数据源、付费模型配置或自己新增角色。导航可见不代表授权。

## 必须通过的未来B负例

两个独立浏览器不能互读；跨店404；改role/tenant字段422或忽略不得赋权；admin无grant403；persona切换后旧CSRF/迟到响应/旧WebActor拒绝；TTL、撤权、logout、重置立即失效；写请求无Origin、错Origin、错CSRF均403；GET按API的同源FetchMetadata受限例外；重复/并发同key一次效果，异文409；reset与写竞争原子；第4/5访客按配置限流且前3不受影响；回收仅tenant owned记录。所有为计划，当前无API/PG/Web运行。

## A独审修订：bootstrap与generation恢复边界

仅session_create的原bootstrap owner可在300秒内读取自己单个原key的最小提交/UNKNOWN状态，不可取新cookie、业务数据或转为active；具体字段、反探测与过期规则以API合同恢复节为准。其余operations必须当前有效DemoSession，logout/过期/撤权后无恢复特权。

所有敏感响应必须有服务端context，浏览器切换开始清屏；同源标签失效通知+每5秒可见页只读current/恢复前强制校验，通知不授予权限。跨设备已显示像素不承诺即时撤屏；服务端旧epoch/generation立即拒绝。GET缺Origin的同源FetchMetadata/Host严格策略和POST强制Origin+CSRF详见API合同，同源GET例外不得传递给任何写入。

## 身份桥接的冻结不变量与专项Gate

V4公开demo bearer的hash只能命中新DemoSession，绝不能也是旧business.web_sessions.token_hash。V4 cookie改名为commerceops_session再请求/api/v1必须401，不能绕过epoch、persona或30min TTL。bound旧WebSession行仅供私有WebActor证据引用，token不得发布、日志或响应暴露；其absolute/idle上界均不得超过原DemoSession绝对截止。

V4 resolver从demo bearer解析当前绑定，核DemoSession/tenant/current principal/epoch/generation，并按旧SessionStore完整规则核当前enabled credential、identity映射、principal enabled/auth_version、bound session身份元组/撤权/到期；不是只调用较窄actor_guard即可。后续调用既有用例时必须包在持V4上下文的guard中，禁止将裸WebActor当作绕过V4 epoch的通行证。V4-0不开放旧业务mutating路径、不提交Graph任务。

persona/reset必须在同一事务中撤销旧bound WebSession并建立新bound身份引用、推进generation/epoch和CSRF；旧actor_guard即使不认识V4字段也因旧bound session已撤销而拒绝。公开demo定位cookie可保持，但它解析到的current binding已经变化，旧CSRF/expected_generation拒绝，绝不原地改旧session principal而让旧actor继续有效。logout/到期/撤权须同样拒绝bound身份；到期即使清理尚未执行也由时间guard拒绝。撤销副作用、receipt和当前绑定必须原子。

实施前SCHEMA/API必须专项给出真实SQL/锁顺序/低权ACL和上述映射证明；必要窄helper若要触及旧web_sessions.py须ROOT另行精确释放并保持旧路由回归，不可自行扩授权/免密码登录。专项审查未通过只停身份桥接，不以候选合同代签代码。
