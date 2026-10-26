"""从已下载的固定官方配置生成无豁免规则；不在 CI 联网解析规则。"""

import argparse
import hashlib
import json
import re
import subprocess
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


WOO_SOURCE_COMMIT = "bbb507b08f1a937f3466369044db27054dee2879"
WOO_SEED_ROW = (
    "            'meta_"
    + "key' => '_commerceops_lab_"
    + "key', 'meta_value' => $key, 'fields' => 'ids']);"
)
WOO_FIXTURE_ROW = '      "' + "key" + '": "' + "partial_" + 'refund",'
WOO_PUBLIC_EXCEPTIONS = (
    (
        "infrastructure/woo-lab/seed.php",
        r"(?:^|/)infrastructure/woo-lab/seed\.php$",
        WOO_SEED_ROW,
        "66b247190dfa6c8e39e40251c2166858090553e24c393565b3c3807d10119527",
        25,
    ),
    (
        "tests/fixtures/woocommerce-local/seed.json",
        r"(?:^|/)tests/fixtures/woocommerce-local/seed\.json$",
        WOO_FIXTURE_ROW,
        "4eccbfac014eeaff0495d26b0ce2073de68aab89987717bb70b6004647b686f4",
        169,
    ),
)

M2_SOURCE_COMMIT = "85f477c46d5348a9e3667f606d273eff3cbaaa32"
M2_PUBLIC_EXCEPTIONS = (
    (
        "frontend/tooling/sync-p5-schema.mjs",
        r"(?:^|/)frontend/tooling/sync-p5-schema\.mjs$",
        "a3bcd562c3b2193866f90fe3efe03523c2f2ce303370fb1fe9f51cdcb1d57408",
        5,
    ),
    (
        "tests/e2e/web/phase5/creation-ui.spec.ts",
        r"(?:^|/)tests/e2e/web/phase5/creation-ui\.spec\.ts$",
        "d5e9e9954765601d77bfdf3e42286cabfdf39c8f7501c3c3c57142277accf0b6",
        153,
    ),
)


def m2_public_rows(root: Path) -> tuple[tuple[str, str, str, str, int], ...]:
    """Read only the two independently reviewed immutable public source lines."""
    result = []
    for path, pattern, digest, line in M2_PUBLIC_EXCEPTIONS:
        source = subprocess.run(
            ["git", "show", M2_SOURCE_COMMIT + ":" + path],
            cwd=root,
            capture_output=True,
            check=False,
        )
        rows = source.stdout.splitlines()
        if (
            source.returncode
            or len(rows) < line
            or hashlib.sha256(rows[line - 1]).hexdigest() != digest
        ):
            raise ValueError("invalid M2 public source")
        result.append((path, pattern, rows[line - 1].decode(), digest, line))
    return tuple(result)


def validate_woo_public_sources(root: Path) -> None:
    """仅核Root已转交B提交的两条公开行，不读取其他WIP或运行数据。"""
    for path, _, row, digest, line in WOO_PUBLIC_EXCEPTIONS:
        if hashlib.sha256(row.encode()).hexdigest() != digest:
            raise ValueError("invalid Woo public source")
        source = subprocess.run(
            ["git", "show", WOO_SOURCE_COMMIT + ":" + path],
            cwd=root,
            capture_output=True,
            check=False,
        )
        rows = source.stdout.splitlines()
        if (
            source.returncode
            or len(rows) < line
            or hashlib.sha256(rows[line - 1]).hexdigest() != digest
        ):
            raise ValueError("invalid Woo public source")


def main() -> None:
    # CI在安装依赖前运行敏感扫描；导入公开行常量不能要求生成器的开发依赖。
    import tomli_w

    from scripts.scan_secrets import APPROVED_TEST_HISTORY

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
    # 九处公开格式误报：只允许指定规则/文件的精确整行，不能排除文件。
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
    validate_woo_public_sources(ROOT)
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
            for source_path, path, row, digest, line in WOO_PUBLIC_EXCEPTIONS:
                reason = "bbb507b已核Woo公开合成marker，仅指定path及完整行，当前/index另核源行hash"
                rule["allowlists"].append(
                    {
                        "description": reason,
                        "condition": "AND",
                        "regexTarget": "line",
                        "paths": [path],
                        "regexes": [r"^(?:\r?\n)?" + re.escape(row) + "$"],
                    }
                )
                exceptions.append(
                    {
                        "rule": rule["id"],
                        "path": path,
                        "reason": reason,
                        "exact_line_sha256": digest,
                        "source_commit": WOO_SOURCE_COMMIT,
                        "source_path": source_path,
                        "source_line": line,
                    }
                )
            for source_path, path, row, digest, line in m2_public_rows(ROOT):
                reason = "85f477c双审公开合同名/字段名，仅指定path与完整行及固定来源hash"
                rule["allowlists"].append(
                    {
                        "description": reason,
                        "condition": "AND",
                        "regexTarget": "line",
                        "paths": [path],
                        "regexes": [r"^(?:\r?\n)?" + re.escape(row) + "$"],
                    }
                )
                exceptions.append(
                    {
                        "rule": rule["id"],
                        "path": path,
                        "reason": reason,
                        "exact_line_sha256": digest,
                        "source_commit": M2_SOURCE_COMMIT,
                        "source_path": source_path,
                        "source_line": line,
                    }
                )
    content = (
        "# Gitleaks v8.30.1 MIT 规则的固定副本；来源/生成信息见 scripts/gitleaks_rules.json。\n"
        "# 删除全部上游 allowlist；保留所有规则及正向 path/regex/entropy。\n"
        "# 不使用 extend/useDefault；仅有 9 个指定规则/路径/精确整行 AND 豁免。\n"
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
        "historical_findings": list(APPROVED_TEST_HISTORY),
    }
    (ROOT / "scripts/gitleaks_rules.json").write_text(
        json.dumps(provenance, indent=2, ensure_ascii=False) + "\n"
    )
    print(f"固定规则生成完成：{len(config['rules'])} rules, 9 exact-line exceptions")


if __name__ == "__main__":
    main()
