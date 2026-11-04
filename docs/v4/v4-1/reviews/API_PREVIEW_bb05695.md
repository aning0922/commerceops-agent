# V41 preview纯策略独立审查

日期：2026-11-04（台北）。source `bb05695b3a2695e494a11dd28353c77ade5af82e`，tree `4c9fdaa8f36b5ab3d32e1a124e09b1b024166492`。完整读取previews.py/test_previews.py以及ImportJobRef和生成schema增量，不读后续SQL/WIP。

结论：ACCEPT_PURE_PREVIEW_POLICY。未发现阻断此纯策略切片的新P1/P2；parser ec0ccf2的P2-I01/I02仍HOLD，不因CSV策略测试通过而关闭。此接受不签持久并发、身份权限、CPU槽位或导入完整Gate。

## 已核不变量

- scope包含tenant/shop/owner/principal/epoch/generation，当前session到期和请求shop/epoch/gen先校验；原owner+preview_key先查历史并比较规范请求digest，原结果早于新效果data_revision CAS返回。跨身份拒绝、异文冲突；只读lookup不因缺行推回滚。
- 新job检查tenant历史12条上限、job ID唯一、父归属/同文件digest/未过期、父无后继且非confirmed；版本严格父+1且最多5。active heads按当前epoch/gen、未过期、未superseded/confirmed计算，替换活动父不多占一个head，最多3。
- 只创建新PreviewRecord，不就地改写父记录；是否superseded由完整历史中的子引用判定。真正两请求互斥、创建子与supersede原子性仍依赖同一tenant锁和SQL约束，纯函数不声称已经提供。
- job ref新增data_revision和固定parser/import-schema version；job digest包含scope、preview data、normalized/request/mapping摘要。normalized内容含解析/导入版本；到期为十分钟与session deadline较早者。
- confirm_new_preview明确只处理新效果：当前身份先核，保存scope/ref、请求、当前revision一致；job version/digest、重新算normalized和job digest匹配；拒过期/不可确认/有后继/已确认，重复SKU及单批1—500范围拒绝。原已提交业务action receipt应由store在调用前检查。

## 必须保留的store接缝

纯函数不认证、不查权限、不持锁。history/confirmed必须来自当前锁内完整权威集合，不能由客户端裁剪，否则head/chain/额度或supersede判断不成立。lookup对其他身份返回UNKNOWN不构成已授权读取。

confirm仅检查单批数量和existing SKU冲突，没有当前已导入数量、shop currency参数；store必须另核本tenant/shop/epoch累计导入不超过500及当前币种。prepare只证明文件digest相同，不重新执行mapping→quality计算；QualityPreview必须来自同一请求/同一文件/映射/币种的受信解析链，不能接受客户端或跨请求缓存任意拼装。落job和confirm都必须重核当前授权/context/TTL、文件和映射绑定。

原键prepare重放返回原记录，不表示原preview仍可确认；服务应结合当前superseded/confirmed/expired状态展示，不把原READY当当前可执行能力。确认回放以原action receipt为准，不再次调用新效果策略。reset后旧generation/epoch及preview不得用新请求恢复权限；tenant总12条历史配额与当前epoch导入配额按合同分别核账。

这些是本片明确的调用边界，须在后续SQL/store接口和故障测试核收；不能只以本纯函数结果签累计额度/事务安全。

## 独立验证

使用git archive从bb05695提取backend/src和原test_previews.py到临时目录，locked Python隔离执行该六项纯测试，native0，6 passed / 0.06秒。一个PytestUnknownMarkWarning来自隔离目录未加载仓库offline marker注册，原样保留；没有因此重跑。测试覆盖原key先于revision、最小lookup、三方revision、摘要篡改、父链/三head/十二job、confirmed终态、跨身份/epoch/gen/expiry及同file绑定。

这是该模块的有限独立纯执行，不是全仓工程检查或作者累计suite；没有数据库、网络、服务、API或浏览器。无效parser语义与硬终止准入另行修复/验证，V40旧失败与UNKNOWN保持。
