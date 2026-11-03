"""每日到期/DST/补最近期与游标签名金标；不启动PG或服务。"""

from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from commerceops.application.daily.contracts import DailyRuleConfig, DailySource
from commerceops.application.daily.cursors import EvidenceContext, decode_cursor, encode_cursor
from commerceops.application.daily.scheduling import ScheduleConfig, due_at, latest_due
from pydantic import ValidationError

from tests.test_daily_report import SOURCE

pytestmark = pytest.mark.offline


def config(
    timezone: str = "America/New_York", delay: int = 60, first: date = date(2026, 3, 6)
) -> ScheduleConfig:
    source = DailySource(**{**SOURCE, "timezone": timezone})
    return ScheduleConfig(
        schema_version="p6-daily-schedule-v1",
        schedule_id=UUID(int=30),
        schedule_version=1,
        organization_id=source.organization_id,
        shop_id=source.shop_id,
        owner_id=UUID(int=40),
        owner_auth_version=1,
        conversation_id=UUID(int=41),
        daily_source=source,
        rules=DailyRuleConfig(currency=source.currency),
        delay_minutes=delay,
        first_business_day=first,
        first_due_at=due_at(first, timezone, delay),
        destination_binding_id=None,
    )


def test_elapsed_delay_respects_spring_and_fall_midnight_boundaries() -> None:
    assert due_at(date(2026, 3, 7), "America/New_York", 60) == datetime(2026, 3, 8, 6, tzinfo=UTC)
    assert due_at(date(2026, 3, 8), "America/New_York", 60) == datetime(2026, 3, 9, 5, tzinfo=UTC)
    assert due_at(date(2026, 10, 31), "America/New_York", 60) == datetime(
        2026, 11, 1, 5, tzinfo=UTC
    )
    assert due_at(date(2026, 11, 1), "America/New_York", 60) == datetime(2026, 11, 2, 6, tzinfo=UTC)


def test_exact_due_and_outage_only_latest_retains_skipped_range() -> None:
    spec = config()
    exact = due_at(date(2026, 3, 12), "America/New_York", 60)
    assert latest_due(spec, spec.first_due_at - timedelta(microseconds=1), None) is None
    period = latest_due(spec, exact, date(2026, 3, 7))
    assert period is not None
    assert period.business_day == date(2026, 3, 12) and period.due_at == exact
    assert (period.missed_periods, period.skipped_first_day, period.skipped_last_day) == (
        4,
        date(2026, 3, 8),
        date(2026, 3, 11),
    )
    assert latest_due(spec, exact, period.business_day) is None
    # last_created是新建游标，不删除3/7已入队的原run。
    from_first = latest_due(spec, exact, None)
    assert from_first is not None and from_first.missed_periods == 6


@pytest.mark.parametrize(
    "zone", ["Asia/Taipei", "America/New_York", "Europe/Berlin", "Pacific/Auckland"]
)
@pytest.mark.parametrize("delay", [0, 60, 1439])
def test_latest_period_never_future_and_next_period_not_yet_due(zone: str, delay: int) -> None:
    spec = config(zone, delay, date(2026, 1, 1))
    for timestamp in (
        datetime(2026, 3, 8, 12, tzinfo=UTC),
        datetime(2026, 11, 1, 23, 59, tzinfo=UTC),
    ):
        period = latest_due(spec, timestamp, None)
        assert period is not None and period.due_at <= timestamp
        assert due_at(period.business_day + timedelta(days=1), zone, delay) > timestamp


def test_schedule_version_and_first_due_binding_rejects_inconsistent_config() -> None:
    body = config().model_dump(mode="json")
    body["first_due_at"] = "2026-03-07T07:00:00Z"
    with pytest.raises(ValidationError, match="DAILY_SCHEDULE_BINDING_INVALID"):
        ScheduleConfig.model_validate_json(__import__("json").dumps(body))


def context() -> EvidenceContext:
    return EvidenceContext(
        actor_id=UUID(int=1),
        auth_version=1,
        organization_id=UUID(int=2),
        shop_id=UUID(int=3),
        task_id=UUID(int=4),
        report_id=UUID(int=5),
        snapshot_id=UUID(int=6),
        content_hash="a" * 64,
        facts_hash="b" * 64,
        question_id=None,
    )


@pytest.mark.parametrize(
    "change",
    [
        {"actor_id": UUID(int=7)},
        {"auth_version": 2},
        {"organization_id": UUID(int=7)},
        {"shop_id": UUID(int=7)},
        {"task_id": UUID(int=7)},
        {"report_id": UUID(int=7)},
        {"snapshot_id": UUID(int=7)},
        {"content_hash": "c" * 64},
        {"facts_hash": "c" * 64},
        {"question_id": UUID(int=7)},
    ],
)
def test_cursor_binds_each_scope_and_report_dimension(change: dict[str, Any]) -> None:
    key = b"owned-test-cursor-material-32-bytes"
    token = encode_cursor(key, context(), 50)
    assert decode_cursor(key, context(), token) == 50
    with pytest.raises(ValueError, match="DAILY_CURSOR_INVALID"):
        decode_cursor(key, context().model_copy(update=change), token)


@pytest.mark.parametrize("token", ["broken", "A" * 5000, "%%%"])
def test_invalid_cursor_fails_closed(token: str) -> None:
    with pytest.raises(ValueError, match="DAILY_CURSOR_INVALID"):
        decode_cursor(b"owned-test-cursor-material-32-bytes", context(), token)
