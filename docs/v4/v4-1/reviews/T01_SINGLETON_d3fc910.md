# V41 T01谓词列最小修复与R3有限事实

日期：2026-11-04（台北）。patch source `d3fc9109a2c6fe37ba2a563095a261afb1625861`，tree `b5a78a9d8ae15e59b501ffaadaac475a5a8e2a05`，parent `9b6fd6afd2fa3dcc9a1eddbe3a514506881520ad`。

结论：ACCEPT_EXACT_TEST_PREDICATE_COLUMN_PATCH。唯一生产外变更为T01 fixture列级SELECT从active_version/config_digest增加singleton，与实际assert_policy的SELECT两列WHERE singleton完全对应。singleton是公开metadata列，未增加整表SELECT、private invocation_verifier、DML或函数权限；原首42501拒绝、缺policy WebFailure、后续激活/轮换断言均保持，所有生产源码不变。

独立确认只发生该一行替换，patch父版本的T01完整函数与实际Root `0d5f848dc9ce78cdc6cb47f6a7feccee8412ba33`相同。可由Root窄cherry-pick此单commit到当前组合，冻结新source/tree/image后开独立新专项22案；不随父链带入e8/CLI，不重跑原失败窗口，不称全仓Full。本轮目标测试仅collect：1节点，native0，1.98秒，无fixture/PG执行。

前次T01_FIXTURE_9f10c8c的源码接受漏核WHERE singleton所需列权限，本次由实际失败纠正；旧源码接受和失败原件均保留，不改写为当时已正确或已通过。

只读核GATES私有 `.audit/v4-1/pg22-root-r3`：closedfinal/safe-failure所绑定原件hash及JUnit相符。实际Root0d5/tree `2255ac42683ecf0e75eee69e0c37cb2ff9811311`，image `sha256:44678112de37b12d163c5abc6c1a0298959f8f51cd2ea74da53052aef00dc2cf`；collect22，实际8=7pass/1fail、14NOT_RUN、0skip，JUnit8.684秒，collect0/pytest1/outer1、no retry。第三个tag golden已PASS；第八T01在可读但未初始化policy分支仍实际42501，未越过该失败签后续测试。

独立closedfinal原件核容器/网络空、CLI group不存活、创建卷与最终保留卷元数据一致、source unchanged。此处只核已有关闭证据，不重新查询运行环境。closedfinal SHA256 `7a589137e1caac8323bd5445d5cbaf915eff1a1746e21e98fcaddb65ec5c65d5`；safe-failure SHA256 `af0e3e465d7de5b0aa87cf5938cd7b81a67836ae1b1efb471b24b3f02fb9cb96`。私有trace只用于匹配安全错误，未抄bearer/CSRF/参数，凭据文件未读。

新修复的实际PG效果仍待新案；旧PG22 R2的2/1/19与R3的7/1/14分开，不拼签全部22。无新Docker、PG、GRANT、native child、服务、浏览器、Full扫描或远端操作。
