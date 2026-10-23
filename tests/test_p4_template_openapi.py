"""新模板分支稳定导出，原 P204 六 schema 完整内容 hash 保持。"""

import hashlib
import json
from pathlib import Path

import pytest
from commerceops.application.replenishment.template_result import P3TemplateRead

pytestmark = pytest.mark.offline


def test_template_openapi_discriminator_strict_refs_and_legacy_schemas_preserved() -> None:
    spec = json.loads(Path("docs/contracts/p3-openapi.json").read_text())
    schemas = spec["components"]["schemas"]
    hashes = {
        "Content": "2fdc121ad29db53ffdc25575208d35d45b8fbf8a2971451d5c6b45109d3e6910",
        "Item": "cacaa8954e006a49bc0f2a99185e89971ca99f9c75ca1bd636af76bf3abf68a6",
        "Metadata": "bbe6a5a05523387a5f5468f106a0dd6448cdb9f696561be32264f129ebd736f5",
        "Refs": "f369f5aee0c5c7d6c95412dff510c2f1c49c504b59e2c25c40b1ef2d018b1fe7",
        "Usage": "ffc523ff8d056491ca4ebe0ea9adc512a509f2661759e05057023245ebc3adac",
        "Read": "dd88c4b8644534180d695ec6a9e711ee0eeb865af40015632fb53a8902ce7fef",
    }
    for suffix, digest in hashes.items():
        raw = json.dumps(
            schemas["P2ExplanationExplanation" + suffix], sort_keys=True, separators=(",", ":")
        ).encode()
        assert hashlib.sha256(raw).hexdigest() == digest
    generated = P3TemplateRead.model_json_schema(
        ref_template="#/components/schemas/P3Template{model}"
    )
    for name, value in generated.pop("$defs").items():
        assert schemas["P3Template" + name] == value
    generated["properties"]["created_at"]["pattern"] = "(Z|[+]00:00)$"
    assert schemas["P3TemplateRead"] == generated
    assert schemas["P3TemplateRead"]["additionalProperties"] is False
    assert "child_task_id" not in schemas["P3TemplateRead"]["properties"]
    branch = schemas["ExplanationRead"]["properties"]["explanation"]
    assert branch["oneOf"][0] == {"$ref": "#/components/schemas/P2ExplanationExplanationRead"}
    assert branch["discriminator"]["mapping"]["p4-p3-template-read-v1"] == (
        "#/components/schemas/P3TemplateRead"
    )
    assert sum(len(value) for value in spec["paths"].values()) == 22
