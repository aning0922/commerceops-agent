"""用项目已锁Ajv2020执行真实DTO同一组wire正负例；不安装或更新依赖。"""

import json
import subprocess
from pathlib import Path

from scripts.export_daily_schema import schema_bytes
from tests.test_daily_read_models import wire_cases

ROOT = Path(__file__).resolve().parents[1]
NODE = r"""
import Ajv2020 from './frontend/node_modules/ajv/dist/2020.js';
import addFormats from './frontend/node_modules/ajv-formats/dist/index.js';
let input = '';
for await (const chunk of process.stdin) input += chunk;
const data = JSON.parse(input);
if (process.version !== 'v24.21.0') throw new Error('locked Node required');
const ajv = new Ajv2020({allErrors: true, strict: true});
addFormats(ajv);
const validate = ajv.compile(data.schema);
for (const [name, body, , expected] of data.cases) {
  const actual = validate(body);
  if (actual !== expected) throw new Error(`case expectation mismatch: ${name}`);
}
console.log(`Ajv2020 strict: ${data.cases.length} cases passed`);
"""


def main() -> None:
    payload = {"schema": json.loads(schema_bytes()), "cases": wire_cases()}
    result = subprocess.run(
        ["node", "--input-type=module", "-e", NODE],
        input=json.dumps(payload),
        text=True,
        cwd=ROOT,
        check=False,
    )
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
