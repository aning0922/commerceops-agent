// Offline strict response validation against the unchanged frozen V4 OpenAPI.
// No HTTP, environment credentials, output payloads, or dependency installation.
import fs from 'node:fs';
import { createRequire } from 'node:module';

const require = createRequire(new URL('../../../frontend/package.json', import.meta.url));
const Ajv2020 = require('ajv/dist/2020.js').default;
const addFormats = require('ajv-formats');
const contract = JSON.parse(fs.readFileSync(new URL('../../../docs/v4/baseline/v4-public-openapi.json', import.meta.url), 'utf8'));
let raw = '';
for await (const chunk of process.stdin) {
  raw += chunk;
  if (raw.length > 1_000_000) throw new Error('bounded input exceeded');
}
try {
  const { operation, status, payload } = JSON.parse(raw);
  const operations = Object.values(contract.paths).flatMap(path => Object.values(path));
  const target = operations.find(op => op.operationId === operation);
  const schema = target?.responses?.[String(status)]?.content?.['application/json']?.schema;
  if (!schema) throw new Error('unlisted operation/status');
  // Only change local reference locations for JSON Schema's standard $defs container.
  const refs = value => {
    if (Array.isArray(value)) return value.map(refs);
    if (value && typeof value === 'object') {
      return Object.fromEntries(Object.entries(value).map(([key, entry]) => [
        key, key === '$ref' ? entry.replace('#/components/schemas/', '#/$defs/') : refs(entry),
      ]));
    }
    return value;
  };
  const ajv = new Ajv2020({ strict: true, allErrors: true });
  addFormats(ajv);
  const validate = ajv.compile({ ...refs(schema), $defs: refs(contract.components.schemas) });
  if (!validate(payload)) {
    // Never print payload values, cookies or safe_message supplied by a server.
    process.stdout.write(JSON.stringify({ valid: false, error_count: validate.errors.length }));
    process.exitCode = 1;
  } else {
    process.stdout.write(JSON.stringify({ valid: true }));
  }
} catch {
  process.stdout.write(JSON.stringify({ valid: false, reason: 'VALIDATOR_OR_CONTRACT_ERROR' }));
  process.exitCode = 2;
}
