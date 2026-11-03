# V4 owned API入口6ca专项审查

日期：2026-11-04（Asia/Taipei）。**结论：P2_REQUIRED_CHANGES，0 P1 / 1 P2；真实监听准备接受暂待密码文件守卫补齐。** 固定容器拓扑与真实app装配本身未发现需放宽旧Settings的问题；不等待未来200%或browser增量。

candidate `6ca19dfc1072baba75af032cfc2cf36822a99cb0` / tree `589dfe9a50d578dbce62f3cc28d38c1b8aad2847`，parent9f3ed5a，4个QA文件。只读精确新增入口/overlay/tests/事实及所用原WebConfig/DatabaseSettings；不读WIP，不启动监听或PG。pilot_b d816失败与停资源保卷为ROOT事实，本轮不复用旧case或重试。

## OWNED-API-01 [P2] runtime-password只绑定名称，未验证实际文件边界

位置：`tests/e2e/v4/owned_api.py:load_owned_config`的database.password_file字符串核验和随后WebConfig.from_file/DemoConfig.load。

入口要求password_file字符串等于/run/v4_api/runtime-password，但没有调用private_bytes或等价文件检查。原WebConfig只对web/demo配置与csrf/nonce秘密应用逐级O_NOFOLLOW、0600、当前UID规则；DatabaseSettings.password()则对password_file直接read_text。因此固定路径上的symlink仍可把实际读取导向目录外，0644文件也被接受，与本入口声明的固定新runtime文件/600边界不符。prepare正常生成600并不等于启动时验证挂载的实际文件。

独立纯反例使用精确6ca模块及其合成config夹具：将runtime-password改为0644，load_owned_config正常返回；再将该固定名改成指向同一Reviewer临时目录内“外部”合成文件的symlink，load_owned_config仍正常返回，web.database.password读取跟随symlink并得到合成哨兵。只输出接受/跟随布尔结果，无真实秘密或DB连接，未访问任何旧资产。

最小修正：在装配原app之前，对固定runtime-password应用现有private_bytes同等的非symlink/逐级路径/普通文件/0600/当前UID约束，保持原数据库配置和loader不变；不要chmod/chown未知挂载来通过。补symlink和0644拒绝、合法600仍接受的纯用例，错误继续固定安全退出。此缺陷仅涉及新owned入口的密码文件核验，不要求重写原API、Settings或连接层。

## 已核固定装配与拓扑

RUNTIME固定/run/v4_api，lstat要求非symlink普通目录、0700且当前UID。拒绝COMMERCEOPS_HOST和任意大写COMMERCEOPS_DB_*环境；P3/V4配置env必须固定到新runtime下web.json/demo.json。预核demo引用的web路径、csrf/nonce路径，DB host=postgres、port5432、user=commerceops_app、v4_demo_库名、无runtime_password_file与commerce_sources；再用真正WebConfig.from_file和DemoConfig.load，不提供旧配置fallback。

COMMERCEOPS_PORT要求规范数字1024–65535，与精确http://127.0.0.1:<port>一致且在受信origins；要求local_http、enabled=true、allow_non_browser_get=false及两次loader的web对象相等。入口用原ReplenishmentStore和create_app显式装配P3+V4，没有StubStore、owner DB连接、自动迁移/grant、worker或代理。原middleware/旧Settings/原API main/Dockerfile均未改。

唯一监听差异是新owned main直接uvicorn固定host0.0.0.0、port已绑、workers1/reloadfalse/proxy_headersfalse/access_logfalse，不能说原main已支持wildcard。overlay仅改command到tests.e2e.v4.owned_api并移除COMMERCEOPS_HOST；宿主ports仍127.0.0.1、PG无host port，API只挂runtime子目录不挂owner secrets。该约束依ROOT新owned容器使用；不准据此在任意宿主直接开放0.0.0.0服务。

## 独立验证与交接

精确6ca快照下定向 **13 PASS / 1.32s / native0**，父进程psycopg.connect额外设为禁止调用。实际ASGI仅验证真实app的Origin403及liveness200；uvicorn.run被截获，未实际listen。旧Settings仍拒绝wildcard、安全错误不回显输入的用例保留。另两项密码文件反例按上文真实复现。全部临时文件已清理，无容器/API/Web/PG操作。

请QA局部补密码文件守卫后交精确普通commit复审，ROOT再开全新pilot。Linux挂载UID/600可读性、实际HTTP/P3改名cookie401、PG鉴权与最终清理仍需该新case证据，不能用13项pure代签。browser2c4与未来native200路径独立审查，不因本入口结论而预签。
