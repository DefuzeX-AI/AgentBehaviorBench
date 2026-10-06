from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


# ImageAsset is the normalized metadata for one extracted image.
class ImageAsset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_id: str = Field(..., min_length=1, description="Stable image identifier.")
    source_file_id: str = Field(..., min_length=1, description="Uploaded source file identifier.")
    source_path: str = Field(..., min_length=1, description="Absolute or runtime-local image path.")
    page_index: int | None = Field(default=None, ge=0, description="0-based page index when available.")
    mime_type: str = Field(..., min_length=3, description="Image MIME type, e.g., image/png.")
    width: int | None = Field(default=None, ge=1, description="Image width in pixels.")
    height: int | None = Field(default=None, ge=1, description="Image height in pixels.")
    caption_hint: str | None = Field(
        default=None,
        min_length=1,
        description="Optional caption or nearby text hint extracted from source document.",
    )


# ReferenceNumeral maps one drawing numeral to a semantic part name.
class ReferenceNumeral(BaseModel):
    model_config = ConfigDict(extra="forbid")

    numeral: str = Field(..., min_length=1, description="Reference numeral appearing on drawings.")
    part_name: str = Field(..., min_length=1, description="Part name aligned with the numeral.")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Extraction confidence score.")


# DrawingRelation describes a semantic relation between two referenced parts.
class DrawingRelation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_numeral: str = Field(..., min_length=1, description="Subject part numeral.")
    predicate: str = Field(..., min_length=1, description="Relation verb, e.g., connected_to.")
    object_numeral: str = Field(..., min_length=1, description="Object part numeral.")
    evidence: str | None = Field(default=None, min_length=1, description="Short supporting evidence text.")


# FigureUnderstanding is one figure-level analysis result.
class FigureUnderstanding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    figure_id: str = Field(..., min_length=1, description="Figure id, e.g., Fig.1.")
    title: str = Field(..., min_length=1, description="Figure title or normalized label.")
    summary: str = Field(..., min_length=10, description="Natural language summary of the figure.")
    reference_numerals: list[ReferenceNumeral] = Field(
        default_factory=list,
        description="Recognized reference numerals in this figure.",
    )
    relations: list[DrawingRelation] = Field(
        default_factory=list,
        description="Detected structural/logical relations between parts.",
    )


# DrawingMap is the structured output of drawing analyzer for drafting workflow.
class DrawingMap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    figures: list[FigureUnderstanding] = Field(
        default_factory=list,
        description="Per-figure analysis results.",
    )
    overall_notes: str = Field(..., min_length=1, description="Overall notes for drawing interpretation.")
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal warnings, e.g., missing numerals.",
    )


# PriorArtVisualDiff stores one visual difference statement for OA rebuttal.
class PriorArtVisualDiff(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature_name: str = Field(..., min_length=1, description="Compared feature label.")
    application_evidence: str = Field(..., min_length=1, description="Visual evidence from the application drawing.")
    prior_art_evidence: str = Field(..., min_length=1, description="Visual evidence from prior-art drawing.")
    difference_assessment: str = Field(
        ...,
        min_length=10,
        description="Assessment of substantive structural/connection differences.",
    )


# PriorArtVisualReport aggregates visual differences for OA strategy support.
class PriorArtVisualReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cited_figure_refs: list[str] = Field(
        default_factory=list,
        description="Figure references cited by examiner or agent, e.g., D1 Fig.2.",
    )
    diffs: list[PriorArtVisualDiff] = Field(
        default_factory=list,
        description="Feature-level visual differences.",
    )
    conclusion: str = Field(..., min_length=10, description="Overall visual comparison conclusion.")
