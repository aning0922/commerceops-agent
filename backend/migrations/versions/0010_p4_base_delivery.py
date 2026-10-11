"""正式Base投影伴随账本；原P3 outbox/probe约束保持。"""

from alembic import op

revision = "0010_p4_base_delivery"
down_revision = "0009_p4_clarification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE business.p4_base_deliveries (
    outbox_id uuid PRIMARY KEY REFERENCES business.outbox(id),
    organization_id uuid NOT NULL,shop_id uuid NOT NULL,task_id uuid NOT NULL,item_id uuid NOT NULL,
    target_key text NOT NULL CHECK(length(target_key) BETWEEN 1 AND 100),
    client_token uuid NOT NULL UNIQUE,version integer NOT NULL CHECK(version BETWEEN 1 AND 2),
    verification_mode text NOT NULL CHECK(verification_mode IN ('offline_fake','controlled_sdk')),
    projection jsonb NOT NULL,projection_hash text NOT NULL CHECK(length(projection_hash)=64),
    status text NOT NULL DEFAULT 'pending'
    CHECK(status IN ('pending','sending','unknown','verified','conflict','fatal','stale')),
    attempts integer NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 3),
    claimed_by text,last_operation text CHECK(last_operation IN ('create','update','reconcile')),
    external_id text,observed_version integer,
    complete_unique_verified boolean NOT NULL DEFAULT false,
    first_attempt_at timestamptz,unknown_since timestamptz,
    last_checked_at timestamptz,last_error text,
    next_attempt_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK((status='verified')=complete_unique_verified),
    CHECK(NOT complete_unique_verified OR (external_id IS NOT NULL AND observed_version=version)),
    CHECK(status<>'sending' OR (attempts>0 AND claimed_by IS NOT NULL
    AND last_operation IS NOT NULL)),
    FOREIGN KEY(item_id) REFERENCES business.replenishment_items(id),
    UNIQUE(organization_id,shop_id,target_key,item_id,version))""")
    op.execute("""CREATE TABLE business.p4_base_links (
    organization_id uuid NOT NULL,shop_id uuid NOT NULL,
    target_key text NOT NULL,item_id uuid NOT NULL,
    original_outbox_id uuid NOT NULL UNIQUE REFERENCES business.p4_base_deliveries(outbox_id),
    external_id text NOT NULL CHECK(length(external_id) BETWEEN 1 AND 256),
    anchored_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY(organization_id,shop_id,target_key,item_id),
    UNIQUE(organization_id,shop_id,target_key,external_id))""")
    op.execute("""CREATE TABLE business.p4_sender_state (
    organization_id uuid NOT NULL,shop_id uuid NOT NULL,
    destination_alias text NOT NULL CHECK(destination_alias IN ('IM','Base')),
    configured_enabled boolean NOT NULL,expires_at timestamptz NOT NULL,
    worker_owner text NOT NULL,worker_backend_pid integer NOT NULL CHECK(worker_backend_pid>0),
    verification_mode text NOT NULL CHECK(verification_mode IN ('offline_fake','controlled_sdk')),
    checked_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY(organization_id,shop_id,destination_alias),
    FOREIGN KEY(organization_id,shop_id) REFERENCES business.shops(organization_id,id))""")
    op.execute("""CREATE FUNCTION business.p4_base_delivery_identity() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN
    IF TG_OP='DELETE' THEN RAISE EXCEPTION 'P4 original projection cannot be deleted'
    USING ERRCODE='23514'; END IF;
    IF TG_OP='INSERT' THEN
      IF NEW.status<>'pending' OR NEW.attempts<>0 OR NEW.unknown_since IS NOT NULL THEN
        RAISE EXCEPTION 'P4 original projection must begin pending' USING ERRCODE='23514';
      END IF;
      IF NOT EXISTS(SELECT 1 FROM business.outbox o JOIN business.replenishment_items i
      ON i.id=o.aggregate_id AND i.organization_id=o.organization_id AND i.shop_id=o.shop_id
      AND i.task_id=o.task_id WHERE o.id=NEW.outbox_id AND o.destination='bitable'
      AND o.operation='item_projection' AND o.source_mode='mock' AND NOT o.sender_enabled
      AND o.organization_id=NEW.organization_id AND o.shop_id=NEW.shop_id AND o.task_id=NEW.task_id
      AND o.aggregate_id=NEW.item_id AND o.aggregate_version=NEW.version
      AND o.provider_idempotency_key IS NOT DISTINCT FROM NEW.client_token
      AND NEW.projection->>'item_id'=NEW.item_id::text
      AND NEW.projection->>'task_id'=NEW.task_id::text
      AND (NEW.projection->>'sync_version')::integer=NEW.version) THEN
        RAISE EXCEPTION 'P4 original projection binding invalid' USING ERRCODE='23514';
      END IF;
    ELSE
      IF (NEW.outbox_id,NEW.organization_id,NEW.shop_id,NEW.task_id,NEW.item_id,NEW.target_key,
      NEW.client_token,NEW.version,NEW.verification_mode,NEW.projection,NEW.projection_hash,NEW.created_at)
      IS DISTINCT FROM (OLD.outbox_id,OLD.organization_id,OLD.shop_id,OLD.task_id,OLD.item_id,
      OLD.target_key,OLD.client_token,OLD.version,OLD.verification_mode,
      OLD.projection,OLD.projection_hash,OLD.created_at)
      OR NEW.attempts<OLD.attempts
      OR (OLD.status IN ('verified','conflict','fatal','stale') AND NEW IS DISTINCT FROM OLD)
      OR (OLD.status='unknown' AND NEW.status NOT IN
      ('unknown','sending','verified','conflict','fatal','stale'))
      OR (OLD.status='unknown' AND NEW.status='sending' AND NEW.last_operation<>'reconcile')
      OR (OLD.external_id IS NOT NULL AND NEW.external_id IS DISTINCT FROM OLD.external_id)
      OR (OLD.first_attempt_at IS NOT NULL
      AND NEW.first_attempt_at IS DISTINCT FROM OLD.first_attempt_at)
      OR (OLD.unknown_since IS NOT NULL AND
      (NEW.unknown_since IS DISTINCT FROM OLD.unknown_since OR NEW.status='pending'
      OR (NEW.status='sending' AND NEW.last_operation<>'reconcile')))
      THEN RAISE EXCEPTION 'P4 projection snapshot or unknown write is immutable'
      USING ERRCODE='23514'; END IF;
    END IF;
    IF NEW.status='unknown' AND NEW.unknown_since IS NULL THEN
      NEW.unknown_since:=clock_timestamp();
    END IF; RETURN NEW; END $$""")
    op.execute("""CREATE TRIGGER p4_base_delivery_identity BEFORE INSERT OR UPDATE OR DELETE
    ON business.p4_base_deliveries FOR EACH ROW
    EXECUTE FUNCTION business.p4_base_delivery_identity()""")
    op.execute("""CREATE FUNCTION business.p4_base_anchor_binding() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN
    IF NOT EXISTS(SELECT 1 FROM business.p4_base_deliveries d
    WHERE d.outbox_id=NEW.original_outbox_id
    AND d.organization_id=NEW.organization_id AND d.shop_id=NEW.shop_id
    AND d.target_key IS NOT DISTINCT FROM NEW.target_key
    AND d.item_id=NEW.item_id AND d.version=1 AND d.status='verified'
    AND d.complete_unique_verified AND d.observed_version=1 AND d.external_id=NEW.external_id) THEN
      RAISE EXCEPTION 'P4 Base anchor requires original full verified v1' USING ERRCODE='23514';
    END IF; RETURN NEW; END $$""")
    op.execute("""CREATE TRIGGER p4_base_anchor_binding BEFORE INSERT ON business.p4_base_links
    FOR EACH ROW EXECUTE FUNCTION business.p4_base_anchor_binding()""")
    op.execute("""CREATE TRIGGER p4_base_anchor_immutable BEFORE UPDATE OR DELETE
    ON business.p4_base_links
    FOR EACH ROW EXECUTE FUNCTION business.reject_inventory_mutation()""")
    for table in ("p4_base_deliveries", "p4_base_links"):
        op.execute(f"""CREATE TRIGGER p4_no_truncate BEFORE TRUNCATE ON business.{table}
        FOR EACH STATEMENT EXECUTE FUNCTION business.reject_inventory_mutation()""")


def downgrade() -> None:
    raise RuntimeError("P4 original projection history cannot be removed destructively")
