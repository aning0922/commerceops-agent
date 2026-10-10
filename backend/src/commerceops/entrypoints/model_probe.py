"""只做非secret配置核验；真实运行必须另用Root明确批准的Worker窗口。"""

import argparse
import json
from pathlib import Path

from commerceops.infrastructure.model_probe_config import verify_config


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["verify-config"])
    parser.add_argument("--key-file", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(verify_config(args.key_file), ensure_ascii=False))
    except Exception:
        raise SystemExit("model probe configuration invalid; raw details withheld") from None


if __name__ == "__main__":
    main()
