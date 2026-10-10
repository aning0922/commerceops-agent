"""P204 组件合同；预算/身份由调用方持久预留，本模块不实现账本。"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol

MODEL = "deepseek-flash"
PROMPT_VERSION = "inventory-explanation-v1"
MAX_INPUT = 8000
MAX_OUTPUT = 800
Mode = Literal["not_used", "offline_stub", "actual_provider"]
ErrorCode = Literal[
    "NO_PROVIDER",
    "INVALID_REPORT",
    "INVALID_REFERENCES",
    "TEMPLATE_REQUIRED",
    "INPUT_BUDGET",
    "TOKEN_COUNT_UNVERIFIED",
    "ADMISSION_REQUIRED",
    "BUDGET_DENIED",
    "ADMISSION_FAILED",
    "TIMEOUT",
    "RATE_LIMIT",
    "PROVIDER_UNAVAILABLE",
    "AUTH_FAILED",
    "BALANCE_EXHAUSTED",
    "HTTP_ERROR",
    "TRANSPORT_ERROR",
    "INVALID_JSON",
    "INVALID_SCHEMA",
    "TRUNCATED",
    "UNSAFE_EXPLANATION",
    "OUTPUT_BUDGET",
    "UNKNOWN_USAGE",
    "UNKNOWN_COST",
    "MODEL_MISMATCH",
    "RESPONSE_TOO_LARGE",
]


@dataclass(frozen=True)
class Message:
    role: Literal["system", "user"]
    content: str


@dataclass(frozen=True)
class TokenCount:
    """必须计完整 chat template（角色/特殊token/生成前缀）；离线计数不能发真实请求。"""

    input_tokens: int
    model: str
    tokenizer_version: str
    evidence: Literal["verified_tokenizer", "offline_stub"]


class TokenCounter(Protocol):
    def count(self, messages: tuple[Message, ...], *, model: str) -> TokenCount: ...


@dataclass(frozen=True)
class Pricing:
    """调用方在授权时复核的 USD/M token 上界；cache 一律按 miss 计。"""

    version: str
    input_per_million: Decimal
    output_per_million: Decimal

    def cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        return (
            input_tokens * self.input_per_million + output_tokens * self.output_per_million
        ) / Decimal(1_000_000)


@dataclass(frozen=True)
class BudgetRequest:
    request_id: str
    request_hash: str
    facts_hash: str
    provider: Literal["deepseek"]
    requested_model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    tokenizer_version: str
    pricing_version: str | None
    cost_upper_bound: Decimal | None
    evidence_mode: Mode


@dataclass(frozen=True)
class Reservation:
    """reserve 必须原子扣占次数/token/金额，返回后即使取消也不可自动释放。"""

    request_id: str
    request_hash: str


class Admission(Protocol):
    async def reserve(self, request: BudgetRequest) -> Reservation | None: ...


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class ModelReply:
    content: str | None = None
    error_code: ErrorCode | None = None
    evidence_mode: Mode = "not_used"
    provider: str | None = None
    requested_model: str | None = None
    returned_model: str | None = None
    prompt_version: str = PROMPT_VERSION
    request_id: str | None = None
    usage: Usage | None = None
    latency_ms: int | None = None
    pricing_version: str | None = None
    cost_estimate: Decimal | None = None
    stop_required: bool = False


class ExplanationProvider(Protocol):
    async def complete(self, messages: tuple[Message, ...], *, facts_hash: str) -> ModelReply: ...


@dataclass(frozen=True)
class ReferenceIds:
    """只接受调用方已核验、授权过的标识；组件不宣称已做DB绑定验证。"""

    snapshot_id: str
    report_id: str


@dataclass(frozen=True)
class ExplanationLine:
    sku_key: str
    reason: str
    text: str
    facts_hash: str
    reference_ids: ReferenceIds | None


@dataclass(frozen=True)
class ExplanationResult:
    facts_hash: str
    narrative_mode: Literal["template", "model_selected"]
    binding_mode: Literal["standalone", "caller_references"]
    summary: str
    lines: tuple[ExplanationLine, ...]
    reference_ids: ReferenceIds | None
    metadata: ModelReply
