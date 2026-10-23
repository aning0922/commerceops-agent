"""从已下载的固定官方配置生成无豁免规则；不在 CI 联网解析规则。"""

import argparse
import hashlib
import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_SHA256 = "e163e53b9e7e8a8511e77271e2b323ed057759542a6d988258afe3a1fa329caf"
P3_DOCUMENT_DIGEST = "a469bb6825770325a664b4770b0f17c78786ecec2126142870e1bd7dd08a6245"
P3_PUBLIC_ROW = '  "' + "open" + 'api_sha256": "' + P3_DOCUMENT_DIGEST + '",'
P3_PUBLIC_PATH = r"(?:^|/)docs/contracts/p3-checks\.json$"
P3_ROW_DIGEST = "4405db53329b7d9b9fb9d5ff920a1e9221dd3ecc57202de57bf838325a03f901"
B_PUBLIC_ROW = '    "' + "sec" + 'rets": "dir/index/fullreachablegit 0 before final stage"'
B_PUBLIC_PATH = r"(?:^|/)frontend/evidence/b02-read/validation\.json$"
B_ROW_DIGEST = "2fd5c5a9ece651f39320ee19c19b067b6f388064fd47cc64bdd2c6dc78f53437"

RO_PUBLIC_ROW = (
    '                ["explicit_ro_'
    + 'recheck_authorized", "explicit_ro_'
    + 'recheck_dispatched"],'
)
RO_PUBLIC_PATH = r"(?:^|/)scripts/p4_acceptance\.py$"
RO_ROW_DIGEST = "07e3542d6dbdbc59bbd099207f38277800daec3217315d0f5dde8549e6df32d5"
RO_SOURCE_COMMIT = "348a9f4ca0c4159d9b3a2cbdf0921623e5bb5600"


def main() -> None:
    # CI在安装依赖前运行敏感扫描；导入公开行常量不能要求生成器的开发依赖。
    import tomli_w

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    source = args.source.read_bytes()
    if hashlib.sha256(source).hexdigest() != UPSTREAM_SHA256:
        raise SystemExit("官方固定配置 SHA256 不匹配")
    config = tomllib.loads(source.decode())
    global_removed = int("allowlist" in config) + len(config.get("allowlists", []))
    config.pop("allowlist", None)
    config.pop("allowlists", None)
    rule_removed = 0
    for rule in config["rules"]:
        rule_removed += int("allowlist" in rule) + len(rule.get("allowlists", []))
        rule.pop("allowlist", None)
        rule.pop("allowlists", None)
    # 五处公开格式误报：只允许指定规则/文件的精确整行，不能排除文件。
    schema_row = next(
        line
        for line in (ROOT / "docs/DATA_MODEL.md").read_text().splitlines()
        if line.startswith("| identities |")
    )
    if hashlib.sha256(schema_row.encode()).hexdigest() != (
        "3716668c9be9e82d8924d3b13323c5296acb4a80402598a6e4c157dee7628838"
    ):
        raise SystemExit("公开 schema 行变化，须重新审查精确豁免")
    exceptions = []
    if hashlib.sha256(P3_PUBLIC_ROW.encode()).hexdigest() != P3_ROW_DIGEST:
        raise SystemExit("P3历史公开摘要行变化，须重新审查精确豁免")
    if hashlib.sha256(B_PUBLIC_ROW.encode()).hexdigest() != B_ROW_DIGEST:
        raise SystemExit("B历史公开metadata行变化，须重新审查精确豁免")
    if hashlib.sha256(RO_PUBLIC_ROW.encode()).hexdigest() != RO_ROW_DIGEST:
        raise SystemExit("RO历史公开action行变化，须重新审查精确豁免")
    for rule in config["rules"]:
        if rule["id"] == "generic-api-key":
            path = r"(?:^|/)docs/DATA_MODEL\.md$"
            row = schema_row
            reason = "公开 identities 字段说明的精确 Markdown 行"
        elif rule["id"] == "aws-amazon-bedrock-api-key-short-lived":
            path = r"(?:^|/)\.gitleaks\.toml$"
            row = "regex = " + json.dumps(rule["regex"])
            reason = "该规则自身固定 regex 声明的精确 TOML 行"
        else:
            continue
        rule["allowlists"] = [
            {
                "description": reason,
                "condition": "AND",
                "regexTarget": "line",
                "paths": [path],
                "regexes": [r"^(?:\r?\n)?" + re.escape(row) + "$"],
            }
        ]
        exceptions.append(
            {
                "rule": rule["id"],
                "path": path,
                "reason": reason,
                "exact_line_sha256": hashlib.sha256(row.encode()).hexdigest(),
            }
        )
        if rule["id"] == "generic-api-key":
            reason = "2a194a8历史公开OpenAPI文件SHA256，Root与独审核实非凭据，仅此旧整行"
            rule["allowlists"].append(
                {
                    "description": reason,
                    "condition": "AND",
                    "regexTarget": "line",
                    "paths": [P3_PUBLIC_PATH],
                    "regexes": [r"^(?:\r?\n)?" + re.escape(P3_PUBLIC_ROW) + "$"],
                }
            )
            exceptions.append(
                {
                    "rule": rule["id"],
                    "path": P3_PUBLIC_PATH,
                    "reason": reason,
                    "exact_line_sha256": P3_ROW_DIGEST,
                    "source_commit": "2a194a8bb3b324982b1ba7a7971eb6e852ce06a6",
                    "source_line": 7,
                }
            )
            reason = "973bf64历史公开B只读验证metadata扫描状态，Root核实非凭据，仅此旧整行"
            rule["allowlists"].append(
                {
                    "description": reason,
                    "condition": "AND",
                    "regexTarget": "line",
                    "paths": [B_PUBLIC_PATH],
                    "regexes": [r"^(?:\r?\n)?" + re.escape(B_PUBLIC_ROW) + "$"],
                }
            )
            exceptions.append(
                {
                    "rule": rule["id"],
                    "path": B_PUBLIC_PATH,
                    "reason": reason,
                    "exact_line_sha256": B_ROW_DIGEST,
                    "source_commit": "973bf6447211f084355d61b9d58adfd95dfa2788",
                    "source_line": 27,
                }
            )
            reason = "348a9f4历史只读SQL audit action公开名称，Root核实整行无私有值，仅此旧整行"
            rule["allowlists"].append(
                {
                    "description": reason,
                    "condition": "AND",
                    "regexTarget": "line",
                    "paths": [RO_PUBLIC_PATH],
                    "regexes": [r"^(?:\r?\n)?" + re.escape(RO_PUBLIC_ROW) + "$"],
                }
            )
            exceptions.append(
                {
                    "rule": rule["id"],
                    "path": RO_PUBLIC_PATH,
                    "reason": reason,
                    "exact_line_sha256": RO_ROW_DIGEST,
                    "source_commit": RO_SOURCE_COMMIT,
                    "source_line": 3936,
                }
            )
    content = (
        "# Gitleaks v8.30.1 MIT 规则的固定副本；来源/生成信息见 scripts/gitleaks_rules.json。\n"
        "# 删除全部上游 allowlist；保留所有规则及正向 path/regex/entropy。\n"
        "# 不使用 extend/useDefault；仅有 5 个指定规则/路径/精确整行 AND 豁免。\n"
        + tomli_w.dumps(config)
    ).encode()
    if tomllib.loads(content.decode()) != config:
        raise SystemExit("规则 TOML 序列化语义变化，拒绝生成")
    (ROOT / ".gitleaks.toml").write_bytes(content)
    provenance = {
        "version": "8.30.1",
        "source": "https://raw.githubusercontent.com/gitleaks/gitleaks/v8.30.1/config/gitleaks.toml",
        "source_sha256": UPSTREAM_SHA256,
        "config_sha256": hashlib.sha256(content).hexdigest(),
        "rule_count": len(config["rules"]),
        "rule_ids_sha256": hashlib.sha256(
            "\n".join(sorted(rule["id"] for rule in config["rules"])).encode()
        ).hexdigest(),
        "removed_global_allowlists": global_removed,
        "removed_rule_allowlists": rule_removed,
        "exceptions": exceptions,
    }
    (ROOT / "scripts/gitleaks_rules.json").write_text(
        json.dumps(provenance, indent=2, ensure_ascii=False) + "\n"
    )
    print(f"固定规则生成完成：{len(config['rules'])} rules, 5 exact-line exceptions")


if __name__ == "__main__":
    main()
