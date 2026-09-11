import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.core.generation_params import (
    AUDIENCE_CATEGORY_IDS,
    DETAIL_LEVELS,
    LANGUAGES,
    OBJECTIVES,
    TONES,
)
from app.core.output_formats import OutputFormat
from app.core.url_policy import UrlPolicyError, parse_url


class GenerationParameters(BaseModel):
    """Per-format generation parameter snapshot.

    Field names and aliases mirror the frontend ``GenerationParams`` shape
    (``frontend/src/lib/types.ts``). Values are validated against the same
    vocabulary the frontend offers, so both sides share one vocabulary.
    """

    model_config = ConfigDict(extra="forbid")

    audience_category: str = Field(
        default="technical", alias="audienceCategory", max_length=50
    )
    target_audience: str | None = Field(
        default=None, alias="targetAudience", max_length=255
    )
    tone: str = Field(default="Authoritative", max_length=50)
    detail_level: str = Field(
        default="Comprehensive Analysis", alias="detail", max_length=50
    )
    objective: str = Field(
        default="Threat Alert & Immediate Containment", max_length=100
    )
    language: str = Field(default="English", max_length=50)

    @field_validator("audience_category")
    @classmethod
    def _validate_audience_category(cls, value: str) -> str:
        if value not in AUDIENCE_CATEGORY_IDS:
            raise ValueError(
                "audienceCategory must be one of "
                + ", ".join(sorted(AUDIENCE_CATEGORY_IDS))
            )
        return value

    @field_validator("tone")
    @classmethod
    def _validate_tone(cls, value: str) -> str:
        if value not in TONES:
            raise ValueError(f"tone '{value}' is not a supported tone")
        return value

    @field_validator("detail_level")
    @classmethod
    def _validate_detail(cls, value: str) -> str:
        if value not in DETAIL_LEVELS:
            raise ValueError(
                "detail must be one of " + ", ".join(sorted(DETAIL_LEVELS))
            )
        return value

    @field_validator("objective")
    @classmethod
    def _validate_objective(cls, value: str) -> str:
        if value not in OBJECTIVES:
            raise ValueError(f"objective '{value}' is not a supported objective")
        return value

    @field_validator("language")
    @classmethod
    def _validate_language(cls, value: str) -> str:
        if value not in LANGUAGES:
            raise ValueError(f"language '{value}' is not a supported language")
        return value

    @field_validator("target_audience")
    @classmethod
    def _strip_target_audience(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()

    def storage_dump(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True, by_alias=False)


class SourceCreate(BaseModel):
    """One ingestible source: exactly one of file / text / URL."""

    model_config = ConfigDict(extra="forbid")

    source_type: Literal["file", "text", "url"]
    input_file_id: uuid.UUID | None = Field(default=None)
    text: str | None = None
    url: str | None = None
    label: str | None = Field(default=None, max_length=255)

    @field_validator("url")
    @classmethod
    def _validate_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        candidate = value.strip()
        try:
            _scheme, _host = parse_url(candidate)
        except UrlPolicyError as exc:
            raise ValueError(str(exc)) from None
        return candidate

    @field_validator("label")
    @classmethod
    def _strip_label(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()

    @model_validator(mode="after")
    def _enforce_exactly_one_payload(self) -> "SourceCreate":
        if self.source_type == "file":
            if self.input_file_id is None:
                raise ValueError("file sources require input_file_id")
        elif self.source_type == "text":
            if self.text is None or not self.text.strip():
                raise ValueError("text sources require non-empty text")
        else:
            if self.url is None or not self.url.strip():
                raise ValueError("url sources require a non-empty url")
        return self


class OutputFormatSelection(BaseModel):
    """A requested output format with its generation parameter snapshot."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    output_format: OutputFormat = Field(alias="outputType")
    parameters: GenerationParameters = Field(default_factory=GenerationParameters)


class TransformationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=255)
    outputs: list[OutputFormatSelection] = Field(min_length=1, max_length=9)
    sources: list[SourceCreate] = Field(default_factory=list, max_length=50)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()

    @field_validator("outputs")
    @classmethod
    def _require_unique_formats(
        cls, selections: list[OutputFormatSelection]
    ) -> list[OutputFormatSelection]:
        formats = [selection.output_format for selection in selections]
        if len(set(formats)) != len(formats):
            raise ValueError("output formats must be unique within a transformation")
        return selections


class TransformationSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_type: str
    label: str | None = None
    input_file_id: uuid.UUID | None = None
    url: str | None = None
    has_text: bool
    text_length: int
    created_at: datetime


class TransformationOutputFormatResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    output_format: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class TransformationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    title: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime
    sources: list[TransformationSourceResponse] = Field(default_factory=list)
    outputs: list[TransformationOutputFormatResponse] = Field(
        default_factory=list,
        validation_alias="output_formats",
    )