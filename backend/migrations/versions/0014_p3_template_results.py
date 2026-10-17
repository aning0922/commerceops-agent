"""P3 原报告/重观测的不可变纯模板；无 child、job、外部发送或历史回填。"""

from alembic import op

revision = "0014_p3_template_results"
down_revision = "0013_p4_first_create"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE business.p3_template_results (
    id uuid PRIMARY KEY,organization_id uuid NOT NULL,shop_id uuid NOT NULL,
    requester_id uuid NOT NULL,p3_task_id uuid NOT NULL,
    source_kind text NOT NULL CHECK(source_kind IN ('p2_original','p3_observation')),
    source_task_id uuid NOT NULL,observation_id uuid,snapshot_id uuid NOT NULL,
    report_id uuid NOT NULL,facts_hash text NOT NULL CHECK(facts_hash ~ '^[a-f0-9]{64}$'),
    template_version text NOT NULL CHECK(template_version='p3-report-template-v1'),
    logical_key text NOT NULL UNIQUE CHECK(logical_key ~ '^p3-template-v1:[a-f0-9]{64}$'),
    status text NOT NULL CHECK(status IN ('ready','unavailable')),safe_error_code text,
    result jsonb,canonical_result text,result_hash text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK((source_kind='p3_observation')=(observation_id IS NOT NULL)),
    CHECK(observation_id IS NULL OR snapshot_id=observation_id),
    CHECK((status='ready' AND safe_error_code IS NULL AND result IS NOT NULL
        AND canonical_result IS NOT NULL AND result_hash IS NOT NULL
        AND canonical_result::jsonb=result
        AND result_hash=encode(sha256(convert_to(canonical_result,'UTF8')),'hex'))
      OR (status='unavailable' AND safe_error_code='TEMPLATE_RENDER_FAILED'
        AND result IS NULL AND canonical_result IS NULL AND result_hash IS NULL)),
    FOREIGN KEY(organization_id,requester_id)
        REFERENCES business.principals(organization_id,id),
    FOREIGN KEY(organization_id,shop_id,p3_task_id)
        REFERENCES business.p3_task_sources(organization_id,shop_id,task_id),
    FOREIGN KEY(organization_id,shop_id,source_task_id)
        REFERENCES business.business_tasks(organization_id,shop_id,id),
    FOREIGN KEY(organization_id,shop_id,p3_task_id,observation_id)
        REFERENCES business.p3_observations(organization_id,shop_id,task_id,id)
    )""")
    op.execute("""CREATE FUNCTION business.p3_bind_template_result() RETURNS trigger
    LANGUAGE plpgsql AS $$
    DECLARE t business.business_tasks; s business.p3_task_sources;
        r business.analysis_reports; o business.p3_observations; m jsonb; l jsonb;
    BEGIN
        IF NEW.logical_key <> 'p3-template-v1:' || encode(sha256(convert_to(
          replace(jsonb_build_array('p3-template-v1',NEW.organization_id::text,
            NEW.shop_id::text,NEW.requester_id::text,NEW.p3_task_id::text,NEW.source_kind,
            NEW.source_task_id::text,NEW.observation_id::text,NEW.snapshot_id::text,
            NEW.report_id::text,NEW.facts_hash,NEW.template_version)::text, ', ', ','),
          'UTF8')),'hex') THEN
          RAISE EXCEPTION 'P3 template logical binding required' USING ERRCODE='23514';
        END IF;
        SELECT * INTO t FROM business.business_tasks WHERE id=NEW.p3_task_id;
        SELECT * INTO s FROM business.p3_task_sources WHERE task_id=NEW.p3_task_id;
        IF t.id IS NULL OR s.task_id IS NULL
          OR t.kind<>'inventory_replenishment'
          OR t.workflow_version<>'p3-inventory-replenishment-v1'
          OR (t.organization_id,t.shop_id,t.requester_id,s.source_task_id) IS DISTINCT FROM
             (NEW.organization_id,NEW.shop_id,NEW.requester_id,NEW.source_task_id) THEN
          RAISE EXCEPTION 'P3 template task/source binding required' USING ERRCODE='23514';
        END IF;
        IF NEW.source_kind='p2_original' THEN
          SELECT * INTO r FROM business.analysis_reports WHERE id=NEW.report_id;
          IF r.id IS NULL OR (r.organization_id,r.shop_id,r.task_id,r.snapshot_id,r.facts_hash)
            IS DISTINCT FROM (NEW.organization_id,NEW.shop_id,NEW.source_task_id,
              NEW.snapshot_id,NEW.facts_hash)
            OR (s.source_report_id,s.snapshot_id,s.facts_hash) IS DISTINCT FROM
              (NEW.report_id,NEW.snapshot_id,NEW.facts_hash)
            OR NOT EXISTS(SELECT 1 FROM business.business_tasks p WHERE p.id=r.task_id
              AND p.kind='inventory_analysis_only'
              AND p.workflow_version='p203-inventory-analysis-v1' AND p.state='completed'
              AND p.requester_id=NEW.requester_id) THEN
            RAISE EXCEPTION 'P3 template completed original report required'
              USING ERRCODE='23514';
          END IF;
        ELSE
          SELECT * INTO o FROM business.p3_observations WHERE id=NEW.observation_id;
          IF o.id IS NULL OR (o.organization_id,o.shop_id,o.task_id,o.source_task_id,
              o.id,o.report_id,o.facts_hash) IS DISTINCT FROM
              (NEW.organization_id,NEW.shop_id,NEW.p3_task_id,NEW.source_task_id,
               NEW.snapshot_id,NEW.report_id,NEW.facts_hash)
             OR (o.original_report_id,o.original_snapshot_id,o.original_facts_hash)
              IS DISTINCT FROM (s.source_report_id,s.snapshot_id,s.facts_hash) THEN
            RAISE EXCEPTION 'P3 template observation binding required' USING ERRCODE='23514';
          END IF;
        END IF;
        IF NEW.status='ready' THEN
          m=NEW.result->'metadata';
          IF NOT COALESCE(NEW.result ?& ARRAY['facts_hash','narrative_mode','binding_mode',
            'summary','lines','reference_ids','metadata']
            AND NEW.result->>'facts_hash'=NEW.facts_hash
            AND NEW.result->>'narrative_mode'='template'
            AND NEW.result->>'binding_mode'='caller_references'
            AND NEW.result#>>'{reference_ids,snapshot_id}'=NEW.snapshot_id::text
            AND NEW.result#>>'{reference_ids,report_id}'=NEW.report_id::text
            AND jsonb_typeof(NEW.result->'lines')='array'
            AND m->>'evidence_mode'='not_used'
            AND m->>'error_code' IN ('NO_PROVIDER','TEMPLATE_REQUIRED')
            AND m->>'prompt_version'='inventory-explanation-v1'
            AND m->'stop_required'='false'::jsonb
            AND m ?& ARRAY['content','provider','requested_model','returned_model','request_id',
                'usage','latency_ms','pricing_version','cost_estimate']
            AND NOT EXISTS(SELECT 1 FROM jsonb_each(m) v
              WHERE v.key IN ('content','provider','requested_model','returned_model',
                'request_id','usage','latency_ms','pricing_version','cost_estimate')
              AND v.value<>'null'::jsonb),false) THEN
            RAISE EXCEPTION 'P3 template typed nonprovider evidence required'
              USING ERRCODE='23514';
          END IF;
          FOR l IN SELECT * FROM jsonb_array_elements(NEW.result->'lines') LOOP
            IF NOT COALESCE(l->>'facts_hash'=NEW.facts_hash
              AND l->'reference_ids'=NEW.result->'reference_ids',false) THEN
              RAISE EXCEPTION 'P3 template line reference required' USING ERRCODE='23514';
            END IF;
          END LOOP;
        END IF;
        RETURN NEW;
    END $$""")
    op.execute("""CREATE TRIGGER p3_template_binding BEFORE INSERT
        ON business.p3_template_results FOR EACH ROW
        EXECUTE FUNCTION business.p3_bind_template_result()""")
    op.execute("""CREATE TRIGGER p3_template_immutable BEFORE UPDATE OR DELETE
        ON business.p3_template_results FOR EACH ROW
        EXECUTE FUNCTION business.reject_inventory_mutation()""")
    op.execute("""CREATE TRIGGER p3_template_no_truncate BEFORE TRUNCATE
        ON business.p3_template_results FOR EACH STATEMENT
        EXECUTE FUNCTION business.reject_inventory_mutation()""")


def downgrade() -> None:
    raise RuntimeError("P3 template history cannot be removed destructively")
