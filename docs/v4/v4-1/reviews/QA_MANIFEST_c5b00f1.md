# V41 owned manifest只读预检独立审查

日期：2026-11-04（台北）。source `c5b00f13e32eaf8538b0386dca374fa78d17cbb0` / tree `2d6395029a93e0f672019ab6631b344ed7d60667`。读取三文件精确增量和所复用V40 validate_subnets实现，不读后续owned driver WIP。

结论：ACCEPT_PUBLIC_PREFLIGHT_ONLY；未发现阻断本只读输入检查切片的新P1/P2。不是服务启动器、授权签名或实际资源核验，不能由preflight成功直接启动旧资源。

固定五scenario、新V41 project/database命名空间、当前UID、未存在canonical case目录、两个不同的整数端口、canonical RFC1918子网/不重叠、精确image-ID形状、UTC父子窗口/1800秒上限/大于180秒剩余、HEAD/tree与clean状态、精确五项公开input集合/hash均有拒绝路径。缺0025/前端schema即拒绝，不回退旧schema。preflight不创建目录/接触镜像/读取私配，明确返回PUBLIC_BINDINGS_VALIDATED_ONLY和runtime NOT_RUN。

边界：image ID在此仅形状合法，端口整数不证明loopback绑定或空闲；namespace前缀不证明资源未被占用，传入now也不是启动时实际时钟。未来driver必须按Root指定精确manifest重新绑定源/时间/实际image及网络端口、创建owned目录并检查权限，不能把此返回值当可复用permit。frozen dataclass里的inputs字典仍可变，消费前应冻结副本或重核，不能预检后修改而继续用旧结果。当前没有启动消费点，因此这些属于后续接缝要求，不是本片运行绕过。

全部scenario统一要求0025和两端schema；早期纯Shell候选缺这些input时应拒绝，Root若另开无业务服务fixture窗口需明确独立合同，不能偷偷省略该集合。README提到62ab为历史导出来源，后续接线应绑定Root已核最新schema而不是使用旧有HOLD版本。

作者 `.audit/v4-1/qa-static-suite-01.xml` 记录25项、0failure/error/skip、4.833秒，其中包括监督模拟与manifest临时公开Git夹具。这里只核JUnit及测试源码，不声称25项均在干净c5b00f1 checkout由Reviewer重跑；也不把schema路径内写入公开fixture文本的测试当真实0025/schema语义验证。无Docker/PG/API/browser/network。
