"""从冻结runtime提取的受限技术核心；实际平台证据不覆盖公开适配版本。"""

from contextlib import contextmanager
from typing import Any

import requests
from urllib3.util import Timeout

from .base_query import QueryOnlySDK, safe_category


class DeadlineQueryOnlySDK(QueryOnlySDK):
    def __init__(self: Any, *a: Any, **k: Any) -> None:
        super().__init__(*a, **k)
        self.http_wait_records: list[dict[str, Any]] = []

    @contextmanager
    def public_HTTP_deadline(self: Any) -> Any:
        original = requests.request

        def bounded(*args: Any, **kwargs: Any) -> Any:
            remaining = self.deadline - 6 - self.clock()
            if remaining <= 0:
                raise TimeoutError()
            seconds = min(5.0, remaining)
            record = dict(
                stage="PUBLIC_HTTP_WITHIN_LIST_SERVICE",
                wait_budget_seconds=seconds,
                http_status=None,
                exception_category=None,
                raw_values_recorded=False,
            )
            self.http_wait_records.append(record)
            kwargs["timeout"] = Timeout(total=seconds, connect=seconds, read=seconds)
            try:
                response = original(*args, **kwargs)
                status = getattr(response, "status_code", None)
                record["http_status"] = status if type(status) is int else None
                if self.clock() >= self.deadline - 6:
                    raise TimeoutError()
                return response
            except Exception as error:
                record["exception_category"] = safe_category(error)
                raise

        requests.request = bounded
        try:
            yield
        finally:
            requests.request = original

    def list(self: Any, *args: Any) -> Any:
        with self.public_HTTP_deadline():
            return super().list(*args)
