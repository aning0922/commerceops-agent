# 最后一项公开位置与浏览器绑定：ROOT 独立增量核收

结论：ACCEPT_PREPARED_DATA_TUPLE_AND_PIN，非运行 Gate。ROOT 未参与 dbe724 / d18df5 作者修改。

对 dbe724e25e11a050dc516d201414a9e082f0befb 读取完整差异：仅原 vendor、provenance、必要负例测试三文件；已审9727文件的一条既核完整行从44移41，列及原span/Match hash全部不变，固定新完整blob锚，旧位置转copy-only，未增任何作者或目录例外。原history、规则文件和classifier字节不变；原222规则/45历史原生例外不减。Root对新集成源实际 validate_rules 通过，作者6项有限负例和native单作者零命中作为独立原回执保留。后续须全量扫描，不以有限结果代签。

对 d18df5a11573a45bf7232d15eaa7d8107bbba3ea，完整差异只有两个来源字段，绑定已由Astra9ccb独审接受的5cc几何取证。Root实际读取原来源全部Git blob，逐项等于PINS，并调用verify_source验证当前集成工作树/HEAD相同。固定命令、单标题、120秒、零重试、其余schema/profile/waiter均不变。作者12项定向纯测保留；新owned浏览器运行及原始PNG/coverage仍待实跑。

本次不读秘密、不启动资源，不改旧失败或业务断言。所有运行证明按实际受测source分别登记。
