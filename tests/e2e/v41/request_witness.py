"""Private original browser POST witnesses; normalize by the reviewed DTO, never send."""

import base64
import hashlib
import json
import re
from typing import Any
from uuid import UUID

from commerceops.application.v41 import contracts as dto

MODELS: dict[str, type[dto.WriteContext]] = {
    "preview": dto.ImportPreviewInput,
    "product_tags": dto.SetProductTags,
    "order_fulfillment": dto.FulfillDemoOrder,
    "import_confirm": dto.ConfirmImport,
}
PATHS = {
    "preview": r"/api/v4/imports/previews",
    "product_tags": r"/api/v4/products/([a-f0-9-]{36})/tags",
    "order_fulfillment": r"/api/v4/orders/([a-f0-9-]{36})/fulfillment",
    "import_confirm": r"/api/v4/imports/([a-f0-9-]{36})/confirm",
}


def canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def validate_request(
    request: dict[str, Any], operation: str, key: str, scope: dict[str, Any]
) -> dict[str, Any]:
    if (
        operation not in MODELS
        or set(request) != {"method", "path", "body", "request_body_sha256"}
        or request["method"] != "POST"
    ):
        raise ValueError("BROWSER_ORIGINAL_REQUEST_FIELDS_REQUIRED")
    match = re.fullmatch(PATHS[operation], request["path"])
    if match is None:
        raise ValueError("BROWSER_ORIGINAL_REQUEST_PATH_REQUIRED")
    if match.groups():
        UUID(match[1])
    body = request["body"]
    raw = canonical(body).encode()
    if len(raw) > 64000 or hashlib.sha256(raw).hexdigest() != request["request_body_sha256"]:
        raise ValueError("BROWSER_ORIGINAL_BODY_HASH_MISMATCH")
    command = MODELS[operation].model_validate_json(raw)
    if (
        str(command.shop_id) != scope["shop_id"]
        or str(command.request_key) != key
        or command.expected_epoch != scope["reset_epoch"]
        or command.expected_generation != scope["auth_generation"]
    ):
        raise ValueError("BROWSER_ORIGINAL_BODY_SCOPE_KEY_MISMATCH")
    return dict(request)


def server_request(request: dict[str, Any], operation: str) -> dict[str, Any]:
    command = MODELS[operation].model_validate_json(canonical(request["body"]))
    if operation == "preview":
        return {
            "command": command.model_dump(mode="json", exclude={"file_base64"}),
            "file_digest": hashlib.sha256(
                base64.b64decode(command.model_dump()["file_base64"], validate=True)
            ).hexdigest(),
        }
    return {"method": "POST", "path": request["path"], "body": command.model_dump(mode="json")}


def match_original_request(attempt: dict[str, Any], actual: str) -> None:
    requests = attempt.get("requests")
    if requests is not None and not any(
        server_request(r, attempt["operation"]) == json.loads(actual) for r in requests
    ):
        raise ValueError("FINAL_BROWSER_ORIGINAL_REQUEST_MISMATCH")
