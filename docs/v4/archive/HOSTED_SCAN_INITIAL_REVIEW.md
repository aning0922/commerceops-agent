# 7ac8fa6 anchor修复增量独审

2026-11-04（台北）。结论：`PRODUCTION_ANCHOR_ACCEPTED / P2_TEST_PORTABILITY_HOLD`。不得以本报告将7ac候选标为无阻断或释放新CI。

source7ac8fa660cea05af3afb9d300a4066e6525c2bf2 / treea96376b697bdeb43ac6f1a21851a5107c44a84b2。四路径为vendor、gitleaks_rules.json、新test_pr53_scan_anchor.py、原test_v4_scan_compat.py；未改受测业务。

## 已核生产边界

独立比较a1fc837与7ac：.gitleaks.toml完整字节相同，SHA256 f15a4c2a47e74a9f14443da3de9b6ecda797c081f89f3ac51cba785a2607ccfe，222条规则；scripts/scan_secrets.py完整字节相同，SHA256 e7c161b4167227ac447f798b6d4aef6edaa94ef06db28041acc1801bb9e17d40。96条exceptions及其余JSON对象全部不变，仅merge-copy anchors末尾追加261来源/path/blob，40→41。vendor除该常量外AST相同，无算法放宽、新行例外或match绑定。

新anchor固定261f39904d8cd5a3d6ae070cdca4a7ae5cde4d6e，path frontend/app/v4/[[...path]]/page.tsx，wholeblob7e2b1229c4544eb751925f38df0ffd5a658cb060。实际98ce merge同路径blob独立匹配。原第9行与63a源字节相同，spanhash87405b72cf4ecad5f2e883918142fa6809f7b0c973fc89881eb429f190a5b64b。

## 实际原件与分轮结果

原件目录 /Users/aipuli/.codex/worktrees/commerceops-pr53-scan-anchor/commerceops-agent/.audit/pr53-scan-anchor-r1 。DELIVERY登记的10项artifacts和4份JUnit hash逐项独立核实相符；JUnit解析分别263/2fail、13/1fail、13/0fail、2/0fail，均errors0/skipped0。不拼称修后263绿。

merge-native.json hash f6f86674059f91099791d2f0d898ce6f5df7cccc485fb505c822499c7d8caf00，实际51 findings；其中该页恰好一条，Commit98ce4a1e523de5bae3eac683728d43f5c6a1c694，RuleID generic-api-key，第9行、StartColumn43/EndColumn116，fingerprint完整对应。Match hash独立计算896d3957535652b65e2eb532731f764c8b1d7f6eafe0bbc90df606658c4b367b，与旧63a snapshot一致，不是17f的42–115 fixture位置。native-checks记录native1/51/0blocking且实际选中finding_source63a；这是原件核对，未在本轮重跑扫描器。final-preflight current/index均0；旧current1及mypy失败仍在原回执中，不覆盖。

## P2：常规offline测试依赖旧临时PR merge对象

位置 tests/test_pr53_scan_anchor.py:14、43–50。MERGE硬编码98ce，module fixture无条件调用真实gitleaks扫描98ce^!；新HEAD的冷CI并不保证具有该旧GitHub合成对象。独立核98ce不是7ac祖先，本地for-each-ref --contains只找到refs/remotes/origin/pr53-merge-evidence-r1。该ref是本地取证引用，不是checkout fetch-depth0自动取得的远端heads/tags或下一次当前PR merge。因此作者本机13/13证明不涵盖冷Hosted对象可用性，下一次Full offline可在fixture失败，阻断CI。

最小修复仅测试：在新临时Git repo使用当前仓库可达261/既有source对象，构造真正双亲merge-copy并真实扫描产生finding，动态绑定该merge SHA；继续精确验证wholeblob、63a span、规则/列/hash和所有拒绝负例。98ce单次原生验证保留私有工程回执，不能做永久测试依赖。不得加联网fetch、缺对象skip或放宽预期集合；生产scanner保持不改。

原wholeblob tamper使用真正双亲临时merge且保留行内容，仅追加空行改变blob，方向正确；其他scope/行列/match/fingerprint/nonmerge拒绝也保留。修复后只需相关定向测试、静态检查及一次输入来自可达对象的证明，不要求重跑全部263或提前触Hosted。Root已独立指出同一阻断并派原owner继续，本报告保留7ac局部通过与该未闭合P2。

本轮只读冻结Git对象和指定原件，独立静态比对命令native0；原review WT未改、未运行测试/服务/CI、未push。后续候选须再次增量核收后由Root决定CI。
