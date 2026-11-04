"""Private bounded parser protocol. It carries no database/session credentials or authority."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from commerceops.application.v4_demo.contracts import Contract, Counter, Currency, Digest
from commerceops.application.v41 import contracts as dto
from commerceops.application.v41.imports import QualityPreview


class ParseInput(Contract):
    format: Literal["csv", "xlsx"]
    file_base64: Annotated[str, Field(min_length=1, max_length=2796204)] = Field(repr=False)
    mapping: dto.ColumnMapping | None
    currency: Currency
    existing_skus: tuple[dto.SkuLabel, ...] = Field(max_length=510)


class ParseResult(Contract):
    schema_version: Literal["v41-parser-result-1"] = "v41-parser-result-1"
    file_digest: Digest
    headers: tuple[Annotated[str, Field(min_length=1, max_length=80)], ...] = Field(
        min_length=1, max_length=24
    )
    row_count: Annotated[int, Field(ge=0, le=500)]
    state: Literal["DISCOVERED", "READY", "INVALID"]
    products: tuple[dto.NormalizedProduct, ...] = Field(max_length=500)
    sample: tuple[dto.ImportSample, ...] = Field(max_length=20)
    issues: tuple[dto.ImportIssue, ...] = Field(max_length=100)
    issue_count: Counter

    @model_validator(mode="after")
    def consistent_quality(self) -> Self:
        if self.state == "READY":
            if not self.products or len(self.products) != self.row_count or self.issue_count:
                raise ValueError("PARSER_RESULT_INVALID")
        elif self.products:
            raise ValueError("PARSER_RESULT_INVALID")
        if len(self.issues) != min(self.issue_count, 100):
            raise ValueError("PARSER_RESULT_INVALID")
        return self

    @classmethod
    def from_quality(cls, quality: QualityPreview) -> "ParseResult":
        return cls(
            file_digest=quality.table.file_digest,
            headers=quality.table.headers,
            row_count=len(quality.table.rows),
            state=quality.state,
            products=quality.products,
            sample=quality.sample,
            issues=quality.issues,
            issue_count=quality.issue_count,
        )
