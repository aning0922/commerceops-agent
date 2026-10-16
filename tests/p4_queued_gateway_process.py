"""Owned child uses the actual serve/SDK connect path with HTTP/WS transport only replaced."""

import sys
from pathlib import Path

from commerceops.entrypoints.feishu_gateway_child import serve
from commerceops.infrastructure.web_config import WebConfig

from tests.p4_queued_transport import install

if __name__ == "__main__":
    config, window, directory = (Path(p) for p in sys.argv[1:])

    from commerceops.adapters.feishu.business_config import BusinessSettings

    business = BusinessSettings.model_validate_json(config.read_bytes())
    web = WebConfig.from_file(business.web_config_file)
    if not web.database.name.startswith(("p3_a01_", "p4_queue_lab_", "p4_acceptance_")):
        raise SystemExit("LAB_DATABASE_REQUIRED")
    install(directory)
    serve(config, window, queued_ready=True)
