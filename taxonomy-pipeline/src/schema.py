"""Canonical schema for all pipeline data structures.

Every stage produces a typed Pydantic model. The CanonicalArtifact
is the final assembly — the contract between Pipeline 1 and Pipeline 2.
"""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


# ─── Enums ───

class BookType(str, Enum):
    TREATISE = "treatise"
    NOVEL = "novel"
    DIALOGUE = "dialogue"
    COLLECTION = "collection"
    MANUAL = "manual"
    POETRY = "poetry"
    RELIGIOUS = "religious"
    ESSAYS = "essays"


class Difficulty(str, Enum):
    ACCESSIBLE = "accessible"
    MODERATE = "moderate"
    CHALLENGING = "challenging"


class SectionType(str, Enum):
    FRONT_MATTER = "front_matter"
    BODY = "body"
    BACK_MATTER = "back_matter"


# ─── Stage 1: Extraction ───

class TocEntry(BaseModel):
    title: str
    page_num: int


class ExtractionResult(BaseModel):
    raw_text: str
    page_count: int
    page_boundaries: list[int]
    has_toc: bool
    toc_entries: list[TocEntry] = Field(default_factory=list)
    is_ocr: bool
    extraction_quality: float


# ─── Stage 2: Cleaning ───

class CleaningResult(BaseModel):
    clean_text: str
    char_count: int
    word_count: int
    cleaning_log: list[str] = Field(default_factory=list)
    content_hash: str


# ─── Stage 3: Structure ───

class StructureResult(BaseModel):
    book_type: str  # Using str instead of BookType for LLM flexibility
    structure_pattern: str
    hierarchy_levels: int
    has_front_matter: bool
    front_matter_types: list[str] = Field(default_factory=list)
    has_back_matter: bool
    back_matter_types: list[str] = Field(default_factory=list)
    confidence: float
    model_used: str = ""


# ─── Stage 4: Boundaries ───

class SectionBoundary(BaseModel):
    id: str
    level: int
    type: str  # front_matter, body, back_matter
    subtype: str  # chapter, introduction, part, etc.
    title: str
    start_offset: int
    end_offset: int = 0  # Computed after all boundaries collected


# ─── Stage 5: Enrichment ───

class NotablePassage(BaseModel):
    text: str
    start_offset: int
    end_offset: int
    significance: str


class SectionEnrichment(BaseModel):
    section_id: str
    summary: str
    key_themes: list[str] = Field(default_factory=list)
    notable_passages: list[NotablePassage] = Field(default_factory=list)
    difficulty: str = "moderate"
    word_count: int = 0
    reading_time_minutes: float = 0.0


# ─── Stage 6: Synthesis ───

class CrossReference(BaseModel):
    from_section: str
    to_section: str
    relationship: str
    note: str = ""


class RoutingHints(BaseModel):
    good_for: list[str] = Field(default_factory=list)
    not_good_for: list[str] = Field(default_factory=list)
    pairs_well_with: list[str] = Field(default_factory=list)


class BookSynthesis(BaseModel):
    domain: str
    subdomains: list[str] = Field(default_factory=list)
    thematic_index: dict[str, list[str]] = Field(default_factory=dict)
    routing_hints: RoutingHints = Field(default_factory=RoutingHints)
    cross_references: list[CrossReference] = Field(default_factory=list)
    model_used: str = ""


# ─── Stage 7: Validation ───

class ValidationResult(BaseModel):
    confidence: float
    flags: list[str] = Field(default_factory=list)
    checks: dict[str, bool] = Field(default_factory=dict)
    passed: bool


# ─── Merged Section (Boundary + Enrichment) ───

class Section(BaseModel):
    """A section with both structural and enrichment data merged."""
    id: str
    level: int
    type: str
    subtype: str
    title: str
    start_offset: int
    end_offset: int
    word_count: int = 0
    reading_time_minutes: float = 0.0
    summary: str = ""
    key_themes: list[str] = Field(default_factory=list)
    notable_passages: list[NotablePassage] = Field(default_factory=list)
    difficulty: str = "moderate"


# ─── The Canonical Artifact ───

class SourceInfo(BaseModel):
    filename: str
    file_hash: str
    page_count: int
    is_ocr: bool
    extraction_quality: float


class TextInfo(BaseModel):
    content: str
    char_count: int
    word_count: int
    content_hash: str
    cleaning_log: list[str] = Field(default_factory=list)


class QualityInfo(BaseModel):
    confidence: float
    flags: list[str] = Field(default_factory=list)
    validation_checks: dict[str, bool] = Field(default_factory=dict)
    human_reviewed: bool = False
    review_status: str = "pending"
    review_notes: Optional[str] = None


class CanonicalArtifact(BaseModel):
    """The single contract between Pipeline 1 and Pipeline 2."""
    artifact_version: str = "1.0.0"
    book_id: str
    generated_at: str
    pipeline_version: str = "0.1.0"
    source: SourceInfo
    text: TextInfo
    structure: StructureResult
    sections: list[Section]
    synthesis: BookSynthesis
    quality: QualityInfo
