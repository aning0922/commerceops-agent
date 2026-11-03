"""显式owner日报来源登记；只消费本次私配的非秘密metadata/manifest，不读取Woo秘密。"""

import argparse
from pathlib import Path
from uuid import UUID

from psycopg.types.json import Jsonb

from commerceops.application.daily.source import DailyUnsafe
from commerceops.domain.commerce_values import canonical_bytes
from commerceops.infrastructure.daily_sources import DailyDeployment, manifest_for
from commerceops.infrastructure.database import DatabaseSettings, connect


def register_source(
    settings: DatabaseSettings, files: DailyDeployment, org: UUID, shop: UUID
) -> UUID:
    binding = files.active(org, shop)
    metadata = files.metadata(binding)
    manifest_for(metadata)
    with connect(settings) as db:
        owner = db.execute("""SELECT current_user=pg_get_userbyid(relowner) AS allowed
        FROM pg_class WHERE oid='business.p6_daily_source_bindings'::regclass""").fetchone()
        if not owner or not owner["allowed"]:
            raise DailyUnsafe("DAILY_PERMISSION_INVALID")
        current = db.execute(
            """SELECT * FROM business.shops WHERE id=%s AND organization_id=%s FOR UPDATE""",
            (shop, org),
        ).fetchone()
        if (
            current is None
            or any(
                current[k] != getattr(metadata, k)
                for k in ("config_ref", "external_shop_key", "environment", "currency", "timezone")
            )
            or current["adapter_kind"] != metadata.adapter_kind
        ):
            raise DailyUnsafe("DAILY_SOURCE_BINDING_CHANGED")
        projection = metadata.model_dump(mode="json")
        inserted = db.execute(
            """INSERT INTO business.p6_daily_source_bindings(id,organization_id,shop_id,
        config_ref,source_config_version,canonical_projection,projection,config_digest)
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING id""",
            (
                binding.binding_id,
                org,
                shop,
                metadata.config_ref,
                metadata.source_config_version,
                canonical_bytes(projection).decode(),
                Jsonb(projection),
                metadata.config_digest,
            ),
        ).fetchone()
        if inserted is None:
            old = db.execute(
                """SELECT * FROM business.p6_daily_source_bindings WHERE id=%s
            AND organization_id=%s AND shop_id=%s""",
                (binding.binding_id, org, shop),
            ).fetchone()
            if (
                old is None
                or old["projection"] != projection
                or old["config_digest"] != metadata.config_digest
            ):
                raise DailyUnsafe("DAILY_SOURCE_BINDING_CHANGED")
    return binding.binding_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Owner-only new owned daily source registration")
    parser.add_argument("--deployment", type=Path, required=True)
    parser.add_argument("--organization", type=UUID, required=True)
    parser.add_argument("--shop", type=UUID, required=True)
    args = parser.parse_args()
    try:
        register_source(
            DatabaseSettings(), DailyDeployment.load(args.deployment), args.organization, args.shop
        )
    except Exception:
        raise SystemExit(
            "daily source registration failed; inspect owned configuration safely"
        ) from None
    print("daily source registered")


if __name__ == "__main__":
    main()
