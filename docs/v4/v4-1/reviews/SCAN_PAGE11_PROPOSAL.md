# V41 stash page11精确copy-only提案裁定

日期：2026-11-04（台北）。本报告为实施范围裁定，不是metadata候选核收或Full扫描通过。

已核私有page11提案SHA256 `581df5fc0799d1c477518f905564ebb6a2904372b37d51182ec3f405c005cf82`。原659 native报告SHA256 `0473ad95c444abdd899b282c049fa19cfb388651399842185fc5937914aa13ea`，实际完整51条，37既有copy/14blocking，不筛成14条。

允许仅新增一条copy-only位置绑定，7→8：source `f949781fa0b9958fedeaf3303c4cf6cefdef8322`，path `frontend/app/v4/[[...path]]/page.tsx`，whole blob `6fe538b6de6f6532a8198476a0ca8a2dd9ca05ee`；line11/end11、columns43—116；span SHA256 `87405b72cf4ecad5f2e883918142fa6809f7b0c973fc89881eb429f190a5b64b`，Match SHA256 `896d3957535652b65e2eb532731f764c8b1d7f6eafe0bbc90df606658c4b367b`。实际native字段与proposal逐项相等，f949第11行span独立重算相等，f949确为单父提交。

旧63a/17f第9行已批准内容与新位置span一致，但不是位置容差。以独立copy-only行11补登记，仍只由既有git范围、至少2parent、精确fingerprint/路径/blob/行列/Match/span算法消费；f949作者单父不能从该绑定得到历史作者批准。stash659三parent、tree等index父、third empty先前已核，不称普通业务merge。

同时仅允许已裁定的六wholeblobanchors候选34→40；152作者批准、96目录项、45native历史allowlist、222规则不变，不加659提交白名单。必须验证51条原件完整分类、作者单父/dir/index拒绝，以及错scope/path/line/column/Match/span/fingerprint/新blob/未授权作者等负例；metadata整包仍要普通commit后精确复审，未经核收不合入或push。

六anchor独立候选预期50copy加page1block的结果只按转交信息登记，本次未运行分类或native扫描，也未修改metadata/refs。新binding候选全部正反例及后续Root唯一全扫描仍pending；原Full失败、已推fcd边界、不可达659历史、预算/UNKNOWN均保留。
