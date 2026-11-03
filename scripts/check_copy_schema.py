"""Independent Ajv2020 strict validation; no dependency install, network or UI build."""

import argparse
import json
import subprocess
from pathlib import Path

from commerceops.entrypoints.knowledge_copy_openapi import copy_openapi

from scripts.export_copy_schema import ROOT, schema_bytes
from tests.test_p6_copy_web_models import wire_cases

NODE = r"""
import {createRequire} from 'node:module';
import {resolve} from 'node:path';
const req = createRequire(resolve(process.argv[1], 'package.json'));
if (req('ajv/package.json').version !== '8.20.0' ||
    req('ajv-formats/package.json').version !== '3.0.1') {
  throw new Error('locked validators required');
}
const Ajv2020 = req('ajv/dist/2020.js').default;
const addFormats = req('ajv-formats').default;
let raw = '';
for await (const chunk of process.stdin) raw += chunk;
const input = JSON.parse(raw);
const ajv = new Ajv2020({allErrors: true, strict: true});
addFormats(ajv);
const validate = ajv.compile(input.schema);
for (const [name, body, , expected] of input.cases) {
  if (validate(body) !== expected) throw new Error(`response case mismatch: ${name}`);
}
// Validate every independently exported operation/request/response schema as well.
const translate = value => {
  if (Array.isArray(value)) return value.map(translate);
  if (value && typeof value === 'object') return Object.fromEntries(
    Object.entries(value).map(([key, item]) => [key,
      key === '$ref' ? item.replace('#/components/schemas/', '#/$defs/') : translate(item)]));
  return value;
};
const defs = translate(input.openapi.components.schemas);
let operations = 0;
for (const methods of Object.values(input.openapi.paths)) {
 for (const operation of Object.values(methods)) {
  const schemas = Object.values(operation.responses).map(
    response => response.content['application/json'].schema);
  if (operation.requestBody) schemas.push(operation.requestBody.content['application/json'].schema);
  for (const schema of schemas) ajv.compile({...translate(schema), $defs: defs});
  operations++;
 }
}
console.log(`Ajv2020 8.20.0 / formats 3.0.1 / ${process.version}: ` +
  `${input.cases.length} cases, ${operations} operations strict passed`);
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dependency-root", type=Path, default=ROOT / "frontend")
    parser.add_argument("--node", default="node")
    args = parser.parse_args()
    payload = {
        "schema": json.loads(schema_bytes()),
        "cases": wire_cases(),
        "openapi": copy_openapi(),
    }
    result = subprocess.run(
        [args.node, "--input-type=module", "-e", NODE, str(args.dependency_root)],
        input=json.dumps(payload),
        text=True,
        cwd=ROOT,
        check=False,
    )
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
