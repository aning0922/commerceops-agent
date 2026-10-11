"""P4正式入口的配置核实命令；真实Gateway启动待Root审后受控窗口。"""

import argparse
import json
from pathlib import Path

from commerceops.adapters.feishu.business_config import verify_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Formal Feishu business configuration")
    parser.add_argument("action", choices=["verify-config"])
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(verify_config(args.config), sort_keys=True))
    except Exception:
        raise SystemExit("P4_CONFIGURATION_INVALID") from None


if __name__ == "__main__":
    main()
