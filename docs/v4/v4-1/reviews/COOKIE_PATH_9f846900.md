# V41 Shell cookie查询URL窄修独审

日期：2026-11-04（台北）。source `9f84690011150689bd31e881482bf4412018a545`，tree `76991ce9cdd2403d7e548f0149b553305e182044`，parent `8f6687560bb5c71804fd249068e2a9912fe35556`。唯一Shell spec，+5/-4。

结论：ACCEPT_EXACT_SESSION_COOKIE_URL_PATCH，未见P1/P2。固定sessionCookieURL=api+'/api/v4/demo/session'统一四处cookies参数；独立反向替换该常量声明和四个参数后与parent逐字节相同。未改生产COOKIE名commerceops_v4_demo、set/delete Path=/api/v4、权限、配置、timeout、业务或测试断言。

旧根URL pathname='/'不匹配cookie Path='/api/v4'；新真实session路径匹配。前置同名cookie长度1、原五项身份/creation key、same-cookie等值、原shop及两处logout后同名cookie长度0均保持，因而logout检查不再能靠根路径空集假通过。Native仍使用同一context在该session URL适用的当前cookie，连同已核nativeSession.context和原nativeShop传给既有caller；不新造会话、不改cookie内容、不过滤掉应当被核验的auth cookie，也不新增cookie值输出或safe字段。Native的既有同访客/私有profile/只读准入仍由原已审实现负责，本片未放宽。

只读safe证据：pure.safe SHA256 `b3dd5884f647e4853a0c8f6c4b5388cf65b6a14e8ee66f30929804b97700add4`，记录原生0、纯filterCookies root0/session1/removal0、无cookie值/无browser/service；独立确认其函数source SHA `fec28a1c8a0026349f747f18f910ac2d2a422720ea10ee28d65f070633f03f00` 与已装Playwright1.64.0原函数精确相符。collect.safe SHA `1c0bae45e1ab2ddc1ed5af925cfdb9d8e6d53f16c984de5e46266b118cb3501d`，绑定candidate Shell SHA `27e6a81f2998ab046e2085b56eb2f032448d4f3b243064b69c13cbc9858b3489`，native0/固定2titles/执行0/无runtime authorization；使用Node sentinel只做collect，不冒CFT启动证明。

本轮未重跑type/collect/pure或任何服务，仅独立源码与safe hash核验；作者type0按作者证据保留。未读取cookie/auth/session/headers私密原件。8f668/r3原cookie长度0失败和cleanup保留，业务partial与三宽截图不提升整案；本修复不签实际offline/hidden、logout、迟到ACK或Native已通过。后续按Root新source归档镜像与运行回执另核。
