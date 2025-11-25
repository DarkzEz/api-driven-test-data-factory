"""Validated config and api contract models"""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

ScenarioName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=3,
        max_length=64,
        pattern=r"^[a-z][a-z0-9-]*$",
    ),
]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
BodyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
HexColor = Annotated[str, StringConstraints(pattern=r"^#[0-9a-fA-F]{6}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class GenerationOptions(StrictModel):
    count: int = Field(ge=1, le=500)
    seed: int = Field(ge=0, le=2**31 - 1)


class StylePreset(StrictModel):
    font_family: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    font_size_px: int = Field(ge=8, le=96)
    color: HexColor
    background_color: HexColor
    bold: bool = False


class ContentTemplate(StrictModel):
    id_prefix: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=2,
            max_length=30,
            pattern=r"^[a-z][a-z0-9-]*$",
        ),
    ]
    titles: list[ShortText] = Field(min_length=1, max_length=100)
    bodies: list[BodyText] = Field(min_length=1, max_length=100)
    styles: list[StylePreset] = Field(min_length=1, max_length=50)


class FactoryConfig(StrictModel):
    scenario: ScenarioName
    generation: GenerationOptions
    template: ContentTemplate


class ContentStyle(StrictModel):
    font_family: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    font_size_px: int = Field(ge=8, le=96)
    color: HexColor
    background_color: HexColor
    bold: bool


class RecordMetadata(StrictModel):
    scenario: ScenarioName
    seed: int = Field(ge=0, le=2**31 - 1)
    sequence: int = Field(ge=1, le=500)


class GeneratedRecord(StrictModel):
    external_id: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    title: ShortText
    body: BodyText
    style: ContentStyle
    metadata: RecordMetadata


def _content_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _validate_batch_items(
    scenario: str,
    seed: int,
    items: list[GeneratedRecord],
) -> None:
    external_ids = [item.external_id for item in items]
    if len(external_ids) != len(set(external_ids)):
        raise ValueError("external_id values must be unique within a batch")

    for expected_sequence, item in enumerate(items, start=1):
        if item.metadata.scenario != scenario:
            raise ValueError("each item's metadata.scenario must match the batch scenario")
        if item.metadata.seed != seed:
            raise ValueError("each item's metadata.seed must match the batch seed")
        if item.metadata.sequence != expected_sequence:
            raise ValueError("metadata.sequence values must be contiguous and start at 1")


class DataBatch(StrictModel):
    scenario: ScenarioName
    seed: int = Field(ge=0, le=2**31 - 1)
    items: list[GeneratedRecord] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def items_match_batch(self) -> DataBatch:
        _validate_batch_items(self.scenario, self.seed, self.items)
        return self

    @property
    def batch_id(self) -> str:
        """Return a stable id for the exact batch contents"""
        return _content_digest(self.model_dump(mode="json"))

    def to_payload(self) -> dict[str, object]:
        """Return the wire payload, including its content derived idempotency key"""
        payload = self.model_dump(mode="json")
        payload["batch_id"] = _content_digest(payload)
        return payload


class IncomingBatch(StrictModel):
    scenario: ScenarioName
    seed: int = Field(ge=0, le=2**31 - 1)
    items: list[GeneratedRecord] = Field(min_length=1, max_length=500)
    batch_id: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]

    @model_validator(mode="after")
    def batch_id_matches_contents(self) -> IncomingBatch:
        _validate_batch_items(self.scenario, self.seed, self.items)
        expected = DataBatch(scenario=self.scenario, seed=self.seed, items=self.items).batch_id
        if self.batch_id != expected:
            raise ValueError("batch_id does not match the batch contents")
        return self


class PublishReceipt(StrictModel):
    status: Literal["accepted"]
    batch_id: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
    accepted_count: int = Field(ge=0)
    duplicate: bool = False

    @field_validator("accepted_count")
    @classmethod
    def accepted_count_must_be_reasonable(cls, value: int) -> int:
        if value > 500:
            raise ValueError("accepted_count cannot exceed the configured batch limit")
        return value
