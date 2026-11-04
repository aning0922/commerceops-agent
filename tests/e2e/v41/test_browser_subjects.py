"""Real local Node file journal components only; no browser, HTTP or database."""

import json
import subprocess
from pathlib import Path

import pytest

from .process import ROOT

pytestmark = pytest.mark.offline


def test_shared_writer_fsyncs_original_body_before_caller_can_continue(tmp_path: Path) -> None:
    tmp_path.chmod(0o700)
    script = r"""
import assert from 'node:assert/strict';
import {readFileSync,
writeFileSync,
chmodSync,
symlinkSync,
unlinkSync} from 'node:fs';
const {subjectWriter,
readBrowserCase}=await import(process.argv[1]);
const directory=process.argv[2],
now=Date.now();
const c={directory,
source_sha:'a'.repeat(40),
source_tree:'b'.repeat(40),
scenario:'shell_navigation',
api_port:18501,
web_port:13501,
uid:process.getuid(),
project:'v41qa_browser_fixture',
starts_at:new Date(now-1000).toISOString(),
deadline:new Date(now+600000).toISOString(),
parent_deadline:new Date(now+900000).toISOString()};
const path=directory+'/case.json';writeFileSync(path,
JSON.stringify(c),
{mode:0o600});process.env.V41_CASE_FILE=path;
assert.deepEqual(readBrowserCase(),
c);
const context={tenant_id:'11111111-1111-4111-8111-111111111111',
organization_id:'22222222-2222-4222-8222-222222222222',
principal_id:'33333333-3333-4333-8333-333333333333',
reset_epoch:0,
auth_generation:1};
const shop='44444444-4444-4444-8444-444444444444',
key='55555555-5555-4555-8555-555555555555';
const body={shop_id:shop,
request_key:key,
expected_epoch:0,
expected_generation:1,
expected_data_revision:'c'.repeat(64),
expected_version:1,
tags:['QA']};
const request={method:'POST',
path:'/api/v4/products/66666666-6666-4666-8666-666666666666/tags',
body};
const w=subjectWriter(c,
'business');w.scope(context,
shop);
w.operation(context,
shop,
'product_tags',
key,
'ATTEMPT_STARTED',
request);
const journal=directory+'/browser-business.subjects.private.jsonl';
const rows=readFileSync(journal,
'utf8').trim().split('\n').map(JSON.parse);
assert.equal(rows.length,
2);assert.deepEqual(rows[1].request.body,
body);assert.match(rows[1].request.request_body_sha256,
/^[a-f0-9]{64}$/);
// The synchronous caller has not sent anything; durable bytes are already independently readable.
assert.throws(()=>w.operation(context,
shop,
'product_tags',
key,
'ATTEMPT_STARTED'));
assert.throws(()=>w.operation(context,
shop,
'product_tags',
key,
'ATTEMPT_STARTED',
{...request,
body:{...body,
headers:{}}}));
assert.throws(()=>w.operation(context,
shop,
'product_tags',
key,
'ATTEMPT_STARTED',
{...request,
path:'/outside'}));
assert.throws(()=>w.operation(context,
shop,
'product_tags',
key,
'ATTEMPT_STARTED',
{...request,
body:{...body,
shop_id:key}}));
assert.equal(readFileSync(journal,
'utf8').trim().split('\n').length,
2);
w.operation(context,
shop,
'product_tags',
key,
'ACK_UNKNOWN');
assert.throws(()=>subjectWriter(c,
'business'));
chmodSync(journal,
0o644);assert.throws(()=>w.scope(context,
shop));chmodSync(journal,
0o600);
unlinkSync(journal);symlinkSync(path,
journal);assert.throws(()=>w.scope(context,
shop));
chmodSync(path,
0o644);assert.throws(()=>readBrowserCase());
process.stdout.write(JSON.stringify({status:'LOCAL_JOURNAL_COMPONENT_PASS'}));
"""
    result = subprocess.run(
        [
            str(ROOT / ".tools/node/bin/node"),
            "--input-type=module",
            "-e",
            script,
            (ROOT / "frontend/v41-e2e/browser-subjects.ts").as_uri(),
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        env={},
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"status": "LOCAL_JOURNAL_COMPONENT_PASS"}
