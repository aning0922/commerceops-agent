// Strict generated V41 response schema; no network or dependency installation.
import fs from 'node:fs';
import { createRequire } from 'node:module';
const require = createRequire(new URL('../../../frontend/package.json', import.meta.url));
const Ajv = require('ajv/dist/2020.js').default;
const formats = require('ajv-formats');
let raw = '';
try {
  for await (const chunk of process.stdin) {
    raw += chunk;
    if (raw.length > 4_000_000) throw new Error('bounded input');
  }
  const input = JSON.parse(raw);
  const contract = JSON.parse(fs.readFileSync(new URL('../../../docs/v4/v4-1/API_CONTRACT.json', import.meta.url)));
  const route = contract.routes.find(r => r.method === input.method && r.path === input.route);
  if (!route || ![200, 201, 400, 401, 403, 404, 409, 410, 413, 422, 429].includes(input.status)) throw new Error('unlisted route/status');
  const ajv = new Ajv({ strict: true, allErrors: true });
  formats(ajv);
  const selected = input.status < 400 ? route.response : route.failure;
  const validate = ajv.compile({ ...selected, $defs: contract.json_schema.$defs });
  const valid = validate(input.payload);
  process.stdout.write(JSON.stringify({ valid: Boolean(valid) }));
  process.exitCode = valid ? 0 : 1;
} catch {
  process.stdout.write(JSON.stringify({ valid: false, reason: 'CONTRACT_OR_VALIDATOR_ERROR' }));
  process.exitCode = 2;
}
