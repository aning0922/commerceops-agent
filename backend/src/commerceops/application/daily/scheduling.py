"""每日到期纯算法：当地午夜转UTC后加elapsed delay，不按24小时累加。"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Literal, Self
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, Field, model_validator

from commerceops.application.daily.contracts import DailyDTO, DailyRuleConfig, DailySource
from commerceops.domain.commerce_values import utc_time


class ScheduleConfig(DailyDTO):
    schema_version: Literal["p6-daily-schedule-v1"]
    schedule_id: UUID
    schedule_version: Annotated[int, Field(ge=1)]
    organization_id: UUID
    shop_id: UUID
    owner_id: UUID
    owner_auth_version: Annotated[int, Field(ge=1)]
    conversation_id: UUID
    daily_source: DailySource
    rules: DailyRuleConfig
    delay_minutes: Annotated[int, Field(ge=0, le=1439)]
    first_business_day: date
    first_due_at: AwareDatetime
    destination_binding_id: UUID | None

    @model_validator(mode="after")
    def bindings(self) -> Self:
        if (
            self.organization_id != self.daily_source.organization_id
            or self.shop_id != self.daily_source.shop_id
            or self.rules.currency != self.daily_source.currency
            or utc_time(self.first_due_at)
            != due_at(self.first_business_day, self.daily_source.timezone, self.delay_minutes)
        ):
            raise ValueError("DAILY_SCHEDULE_BINDING_INVALID")
        return self


@dataclass(frozen=True)
class DuePeriod:
    business_day: date
    due_at: datetime
    missed_periods: int
    skipped_first_day: date | None
    skipped_last_day: date | None


def due_at(day: date, timezone: str, delay_minutes: int) -> datetime:
    if type(delay_minutes) is not int or not 0 <= delay_minutes <= 1439:
        raise ValueError("DAILY_SCHEDULE_DELAY_INVALID")
    midnight = datetime.combine(day + timedelta(days=1), time.min, tzinfo=ZoneInfo(timezone))
    return midnight.astimezone(UTC) + timedelta(minutes=delay_minutes)


def latest_due(
    config: ScheduleConfig, timestamp: datetime, last_created_day: date | None
) -> DuePeriod | None:
    timestamp = utc_time(timestamp)
    # due日的当地午夜可能受DST影响；从当前当地日期向前核实际UTC边界。
    day = timestamp.astimezone(ZoneInfo(config.daily_source.timezone)).date() - timedelta(days=1)
    while due_at(day, config.daily_source.timezone, config.delay_minutes) > timestamp:
        day -= timedelta(days=1)
    if day < config.first_business_day or (
        last_created_day is not None and day <= last_created_day
    ):
        return None
    first_missing = (
        max(config.first_business_day, last_created_day + timedelta(days=1))
        if last_created_day is not None
        else config.first_business_day
    )
    missed = (day - first_missing).days
    return DuePeriod(
        day,
        due_at(day, config.daily_source.timezone, config.delay_minutes),
        missed,
        first_missing if missed else None,
        day - timedelta(days=1) if missed else None,
    )
