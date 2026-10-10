"""T3持久决定/原请求/单resume绑定；A02不允许T4 consumed或执行完成。"""

from alembic import op

revision = "0006_p3_decisions"
down_revision = "0005_p3_approval"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ddl = """ALTER TABLE business.approvals ADD COLUMN ready_checkpoint_id text;
ALTER TABLE business.approvals ADD COLUMN decided_auth_version bigint;
ALTER TABLE business.approvals ADD COLUMN decided_identity_id uuid;
ALTER TABLE business.approvals ADD CHECK((decision_id IS NULL AND decided_auth_version IS NULL
 AND decided_identity_id IS NULL) OR (decision_id IS NOT NULL AND decided_auth_version IS NOT NULL
 AND decided_auth_version>0
 AND decided_identity_id IS NOT NULL));
ALTER TABLE business.approvals ADD FOREIGN KEY(organization_id,decided_identity_id,decided_by)
 REFERENCES business.identities(organization_id,id,principal_id);
ALTER TABLE business.approvals ADD UNIQUE(organization_id,shop_id,task_id,id,decision_id);
ALTER TABLE business.approvals ADD CONSTRAINT a02_no_t4_consumption CHECK(consumed_at IS NULL);
CREATE TABLE business.approval_resumes (
 decision_id uuid PRIMARY KEY,approval_id uuid NOT NULL UNIQUE,
 organization_id uuid NOT NULL,shop_id uuid NOT NULL,task_id uuid NOT NULL,
 job_id uuid NOT NULL UNIQUE REFERENCES business.jobs(id),
 continuation_job_id uuid UNIQUE REFERENCES business.jobs(id),
 delivery_state text NOT NULL CHECK(delivery_state IN ('queued','waiting_checkpoint','consumed')),
 checkpoint_id text,delivered_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 CHECK((delivery_state='consumed')=(delivered_at IS NOT NULL)),
 CHECK(delivered_at IS NULL OR checkpoint_id IS NOT NULL),
 FOREIGN KEY(organization_id,shop_id,task_id,approval_id,decision_id)
 REFERENCES business.approvals(organization_id,shop_id,task_id,id,decision_id)
);"""
    for statement in ddl.split(";"):
        if statement.strip():
            op.execute(statement)
    op.execute("""CREATE FUNCTION business.bind_p3_resume() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM business.jobs j WHERE j.id=NEW.job_id
 AND j.organization_id=NEW.organization_id AND j.shop_id=NEW.shop_id AND j.task_id=NEW.task_id
 AND j.kind='resume' AND j.payload_ref='decision:'||NEW.decision_id::text
 AND j.dedupe_key='p3-decision:'||NEW.decision_id::text) THEN
  RAISE EXCEPTION 'P3 resume job binding mismatch' USING ERRCODE='23514';
 END IF;
 IF NEW.continuation_job_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM business.jobs j
 JOIN business.approvals a ON a.id=NEW.approval_id AND a.decision_id=NEW.decision_id
 WHERE j.id=NEW.continuation_job_id AND j.organization_id=NEW.organization_id
 AND j.shop_id=NEW.shop_id AND j.task_id=NEW.task_id AND j.kind='recover'
 AND j.payload_ref='continue:'||NEW.decision_id::text
 AND j.dedupe_key='p3-continue:'||NEW.decision_id::text AND a.status='approved') THEN
  RAISE EXCEPTION 'P3 continuation binding mismatch' USING ERRCODE='23514';
 END IF;
 IF NEW.delivery_state='consumed' AND NOT EXISTS(SELECT 1 FROM business.approvals a
 WHERE a.id=NEW.approval_id AND a.decision_id=NEW.decision_id
 AND ((a.status='approved' AND NEW.continuation_job_id IS NOT NULL)
 OR (a.status='rejected' AND NEW.continuation_job_id IS NULL))) THEN
  RAISE EXCEPTION 'P3 delivered decision requires its durable continuation' USING ERRCODE='23514';
 END IF;
 IF TG_OP='UPDATE' AND ((NEW.decision_id,NEW.approval_id,NEW.organization_id,NEW.shop_id,
 NEW.task_id,NEW.job_id,NEW.created_at) IS DISTINCT FROM
 (OLD.decision_id,OLD.approval_id,OLD.organization_id,OLD.shop_id,OLD.task_id,OLD.job_id,OLD.created_at)
 OR (OLD.delivery_state='consumed' AND
 (NEW.delivery_state,NEW.checkpoint_id,NEW.delivered_at,NEW.continuation_job_id)
 IS DISTINCT FROM
 (OLD.delivery_state,OLD.checkpoint_id,OLD.delivered_at,OLD.continuation_job_id))) THEN
  RAISE EXCEPTION 'P3 delivered resume is immutable' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$""")
    op.execute("""CREATE TRIGGER bind_p3_resume BEFORE INSERT OR UPDATE
 ON business.approval_resumes FOR EACH ROW EXECUTE FUNCTION business.bind_p3_resume()""")
    op.execute("""CREATE FUNCTION business.p3_ready_once() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (NEW.ready_at IS NULL)<>(NEW.ready_checkpoint_id IS NULL)
 OR (OLD.decision_id IS NOT NULL AND (NEW.decided_auth_version,NEW.decided_identity_id)
 IS DISTINCT FROM (OLD.decided_auth_version,OLD.decided_identity_id))
 OR (OLD.ready_at IS NOT NULL AND (NEW.ready_at,NEW.ready_checkpoint_id)
 IS DISTINCT FROM (OLD.ready_at,OLD.ready_checkpoint_id)) THEN
  RAISE EXCEPTION 'P3 checkpoint ready binding is immutable' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$""")
    op.execute("""CREATE TRIGGER p3_ready_once BEFORE UPDATE ON business.approvals
 FOR EACH ROW EXECUTE FUNCTION business.p3_ready_once()""")
    op.execute("""CREATE FUNCTION business.p3_requests_immutable() RETURNS trigger
 LANGUAGE plpgsql AS $$ BEGIN
 RAISE EXCEPTION 'P3 request receipt is immutable' USING ERRCODE='23514'; END $$""")
    op.execute("""CREATE TRIGGER p3_requests_immutable BEFORE UPDATE OR DELETE
 ON business.web_requests FOR EACH ROW EXECUTE FUNCTION business.p3_requests_immutable()""")
    op.execute("""CREATE TRIGGER p3_requests_no_truncate BEFORE TRUNCATE
 ON business.web_requests FOR EACH STATEMENT EXECUTE FUNCTION business.p3_requests_immutable()""")
    op.execute("""CREATE FUNCTION business.p3_terminal_decision() RETURNS trigger
 LANGUAGE plpgsql AS $$ BEGIN
 IF NEW.kind='inventory_replenishment' AND NEW.state IS DISTINCT FROM OLD.state THEN
  IF NEW.state='rejected' AND NOT EXISTS(SELECT 1 FROM business.approvals a
   JOIN business.approval_resumes r ON r.approval_id=a.id AND r.decision_id=a.decision_id
   WHERE a.task_id=NEW.id AND a.plan_id=NEW.active_plan_id AND a.status='rejected'
   AND r.delivery_state='consumed') THEN
   RAISE EXCEPTION 'P3 rejected requires delivered decision' USING ERRCODE='23514';
  END IF;
  IF NEW.state='expired' AND NOT EXISTS(SELECT 1 FROM business.approvals a
   WHERE a.task_id=NEW.id AND a.plan_id=NEW.active_plan_id AND a.status='expired'
   AND a.expires_at<=clock_timestamp()) THEN
   RAISE EXCEPTION 'P3 expired requires bound expiry' USING ERRCODE='23514';
  END IF;
 END IF;
 RETURN NEW;
END $$""")
    op.execute("""CREATE TRIGGER p3_terminal_decision BEFORE UPDATE ON business.business_tasks
 FOR EACH ROW EXECUTE FUNCTION business.p3_terminal_decision()""")


def downgrade() -> None:
    raise RuntimeError("destructive downgrade disabled; restore a verified backup")
