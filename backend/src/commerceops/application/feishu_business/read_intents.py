"""全文有限显式 reference；无模型路由、代词、最近对象或尾词猜选。"""

import re
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

IDENTIFIER = r"[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}"
STATUS = re.compile(rf"查询任务[ \t]*({IDENTIFIER})[ \t]*进度")
EXPLAIN = re.compile(rf"解释任务[ \t]*({IDENTIFIER})[ \t]*的报告[ \t]*({IDENTIFIER})")


@dataclass(frozen=True)
class ReadIntent:
    kind: Literal["task_status", "explain_report"]
    task_id: UUID
    report_id: UUID | None = None


def parse_read_intent(text: str) -> ReadIntent | None:
    if match := STATUS.fullmatch(text):
        return ReadIntent("task_status", UUID(match[1]))
    if match := EXPLAIN.fullmatch(text):
        return ReadIntent("explain_report", UUID(match[1]), UUID(match[2]))
    return None
