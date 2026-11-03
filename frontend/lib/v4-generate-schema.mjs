import {readFileSync, writeFileSync} from 'node:fs';
const input = new URL('../../docs/v4/baseline/v4-public-openapi.json', import.meta.url);
const output = new URL('./v4-schema.json', import.meta.url);
const spec = JSON.parse(readFileSync(input, 'utf8'));
const definitions = JSON.parse(JSON.stringify(spec.components.schemas).replaceAll('#/components/schemas/', '#/$defs/'));
writeFileSync(output, `${JSON.stringify({$defs: definitions}, null, 2)}\n`);
