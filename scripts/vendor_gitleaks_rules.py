"""从已下载的固定官方配置生成无豁免规则；不在 CI 联网解析规则。"""

import argparse
import hashlib
import json
import re
import tomllib
from pathlib import Path

import tomli_w

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_SHA256 = "e163e53b9e7e8a8511e77271e2b323ed057759542a6d988258afe3a1fa329caf"


def main() -> None:
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
    # 两处公开格式误报：只允许指定规则/文件的精确整行，不能排除文件。
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
    content = (
        "# Gitleaks v8.30.1 MIT 规则的固定副本；来源/生成信息见 scripts/gitleaks_rules.json。\n"
        "# 删除全部上游 allowlist；保留所有规则及正向 path/regex/entropy。\n"
        "# 不使用 extend/useDefault；仅有 2 个指定规则/路径/精确整行 AND 豁免。\n"
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
    print(f"固定规则生成完成：{len(config['rules'])} rules, 2 exact-line exceptions")


if __name__ == "__main__":
    main()
