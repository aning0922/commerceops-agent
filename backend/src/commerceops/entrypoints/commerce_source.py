"""显式 owned-test 部署登记；业务 runtime 不导入或调用此入口。"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb

from commerceops.adapters.commerce.woocommerce_http import invalid_constant, object_pairs
from commerceops.application.commerce.source_binding import (
    RegisteredWooSource,
    SourceBindingError,
    WooSourceMetadata,
)
from commerceops.domain.commerce_values import canonical_bytes
from commerceops.infrastructure.database import DatabaseSettings, connect
from commerceops.infrastructure.web_config import private_bytes


def register_owned_source(
    settings: DatabaseSettings,
    identifier: UUID,
    metadata: WooSourceMetadata,
) -> RegisteredWooSource:
    metadata = WooSourceMetadata.model_validate_json(metadata.model_dump_json())
    if metadata.anchor_day > datetime.now(UTC).astimezone(ZoneInfo(metadata.timezone)).date():
        raise SourceBindingError()
    projection = metadata.model_dump(mode="json")
    registered = RegisteredWooSource(
        binding_id=identifier,
        organization_id=metadata.organization_id,
        shop_id=metadata.shop_id,
        config_ref=metadata.config_ref,
        source_config_version=metadata.source_config_version,
        config_digest=metadata.config_digest,
    )
    with connect(settings) as db:
        shop = db.execute(
            "SELECT * FROM business.shops WHERE organization_id=%s AND id=%s FOR SHARE",
            (metadata.organization_id, metadata.shop_id),
        ).fetchone()
        if shop is None or any(
            shop[field] != getattr(metadata, field)
            for field in (
                "config_ref",
                "adapter_kind",
                "environment",
                "external_shop_key",
                "currency",
                "timezone",
            )
        ):
            raise SourceBindingError()
        db.execute(
            """INSERT INTO business.p5_commerce_source_bindings
            (id,organization_id,shop_id,config_ref,source_config_version,config_digest,
             projection,canonical_projection) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING""",
            (
                identifier,
                metadata.organization_id,
                metadata.shop_id,
                metadata.config_ref,
                metadata.source_config_version,
                metadata.config_digest,
                Jsonb(projection),
                canonical_bytes(projection).decode(),
            ),
        )
        row = db.execute(
            "SELECT * FROM business.p5_commerce_source_bindings WHERE id=%s",
            (identifier,),
        ).fetchone()
        if (
            row is None
            or row["projection"] != projection
            or any(
                row["id" if field == "binding_id" else field] != value
                for field, value in registered.model_dump().items()
            )
        ):
            raise SourceBindingError()
    return registered


def main() -> None:
    parser = argparse.ArgumentParser(description="Register immutable owned Woo test source")
    parser.add_argument("--register-owned-test-source", action="store_true", required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--binding-id", type=UUID, required=True)
    args = parser.parse_args()
    try:
        encoded = private_bytes(args.metadata)
        json.loads(encoded, object_pairs_hook=object_pairs, parse_constant=invalid_constant)
        registered = register_owned_source(
            DatabaseSettings(),
            args.binding_id,
            WooSourceMetadata.model_validate_json(encoded),
        )
        print(json.dumps({"registered": True, "binding_id": str(registered.binding_id)}))
    except Exception as error:
        raise SystemExit(f"source registration failed: {type(error).__name__}") from None


if __name__ == "__main__":
    main()
