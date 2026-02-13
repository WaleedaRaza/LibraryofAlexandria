# Taxonomy Pipeline Architecture

## Overview

Two pipelines. One contract between them: the **Canonical Artifact JSON**.

```
Pipeline 1: PDF → Artifact JSON     (offline, local Mac, Ollama)
Pipeline 2: Artifact JSON → App DB  (admin process, hits Supabase)
```

Everything in this document flows from one principle: **the artifact schema is the source of truth.** Design it right, and both pipelines become straightforward implementations against a known contract.

---

## 1. The Canonical Artifact Schema

This is the single most important thing in the system. Both pipelines exist to produce and consume this structure. Every field here maps to a feature in the app.

```jsonc
{
  // ─── IDENTITY ───
  "artifact_version": "1.0.0",
  "book_id": "meditations__marcus_aurelius",        // slug: title__author
  "generated_at": "2025-02-08T14:30:00Z",
  "pipeline_version": "1.0.0",

  // ─── SOURCE ───
  "source": {
    "filename": "meditations.pdf",
    "file_hash": "sha256:abc123...",                 // hash of original PDF
    "page_count": 142,
    "is_ocr": false,
    "extraction_quality": 0.92                       // 0-1, heuristic from Stage 1
  },

  // ─── CLEAN TEXT (the immutable foundation) ───
  "text": {
    "content": "THE FULL CLEAN TEXT HERE...",
    "char_count": 187432,
    "word_count": 38210,
    "content_hash": "sha256:def456...",              // hash of content — if this changes, all offsets break
    "cleaning_log": [
      "stripped_header: 'MEDITATIONS — MARCUS AURELIUS' from 128/142 pages",
      "stripped_footer: page numbers from 140/142 pages",
      "rejoined_hyphenation: 47 instances",
      "normalized_whitespace: 892 excess newlines removed"
    ]
  },

  // ─── STRUCTURAL CLASSIFICATION ───
  "structure": {
    "book_type": "treatise",                         // treatise|novel|dialogue|collection|manual|poetry|religious|essays
    "structure_pattern": "books > entries",           // human-readable hierarchy description
    "hierarchy_levels": 2,                            // 1=flat, 2=parts>chapters, 3=parts>chapters>sections
    "has_front_matter": true,
    "front_matter_types": ["translator_note", "introduction"],
    "has_back_matter": true,
    "back_matter_types": ["endnotes", "index"],
    "classification_confidence": 0.94,
    "model_used": "llama3.1:8b"
  },

  // ─── SECTIONS (the structural map) ───
  "sections": [
    {
      "id": "fm_001",                                // front matter: fm_NNN
      "level": 0,                                    // 0=top-level, 1=sub, 2=sub-sub
      "type": "front_matter",                        // front_matter|body|back_matter
      "subtype": "translator_note",                  // chapter|part|section|entry|act|scene|introduction|etc
      "title": "Translator's Note",
      "start_offset": 0,                             // character offset into text.content
      "end_offset": 3847,                            // exclusive end
      "word_count": 762,
      "reading_time_minutes": 3.8,

      // ─── Enrichment (from Stage 5) ───
      "summary": "Gregory Hays explains his translation approach, favoring modern English clarity over Victorian formality. He contextualizes Marcus Aurelius as a practicing Stoic who wrote for himself, not for publication.",
      "key_themes": ["translation", "historical_context", "stoicism"],
      "notable_passages": [
        {
          "text": "These are the personal reflections of a man who...",
          "start_offset": 1204,
          "end_offset": 1298,
          "significance": "Establishes that Meditations was never intended for publication"
        }
      ],
      "difficulty": "accessible"                     // accessible|moderate|challenging
    },
    {
      "id": "sec_001",                               // body sections: sec_NNN
      "level": 1,
      "type": "body",
      "subtype": "chapter",
      "title": "Book 1: Debts and Lessons",
      "start_offset": 3847,
      "end_offset": 12340,
      "word_count": 1685,
      "reading_time_minutes": 8.4,
      "summary": "Marcus catalogs what he learned from each person in his life — from his grandfather's character to his philosophy teachers' examples. Each entry is a debt acknowledged.",
      "key_themes": ["gratitude", "mentorship", "character", "self_discipline"],
      "notable_passages": [
        {
          "text": "From my grandfather Verus I learned good morals and the government of my temper.",
          "start_offset": 3860,
          "end_offset": 3942,
          "significance": "Opening line — sets the pattern of learning from others"
        }
      ],
      "difficulty": "accessible"
    }
    // ... more sections
  ],

  // ─── SYNTHESIS (book-level intelligence) ───
  "synthesis": {
    "domain": "philosophy",
    "subdomains": ["stoicism", "ethics", "self_improvement"],

    "thematic_index": {
      // theme → list of section IDs where it appears
      "mortality": ["sec_002", "sec_004", "sec_009"],
      "duty": ["sec_001", "sec_003", "sec_005"],
      "self_discipline": ["sec_001", "sec_003", "sec_007"],
      "impermanence": ["sec_004", "sec_006", "sec_009"],
      "nature_of_universe": ["sec_002", "sec_006", "sec_010"]
    },

    "routing_hints": {
      "good_for": [
        "dealing with things outside your control",
        "finding purpose in daily obligations",
        "accepting mortality",
        "managing anger or frustration",
        "leadership under pressure"
      ],
      "not_good_for": [
        "systematic logical argumentation",
        "understanding Eastern philosophy",
        "detailed historical narrative",
        "romantic or emotional guidance"
      ],
      "pairs_well_with": [
        "Letters from a Stoic — Seneca",
        "Discourses — Epictetus",
        "The Enchiridion — Epictetus"
      ]
    },

    "cross_references": [
      {
        "from_section": "sec_001",
        "to_section": "sec_006",
        "relationship": "elaborates",
        "note": "Book 6 revisits the mentorship themes of Book 1 but with harder-won perspective"
      }
    ],

    "model_used": "llama3.1:8b"
  },

  // ─── QUALITY ───
  "quality": {
    "confidence": 0.87,                              // composite score from validation
    "flags": [],                                     // ["sparse_themes", "boundary_uncertainty", "ocr_artifacts"]
    "validation_checks": {
      "offsets_complete": true,                       // sections cover 100% of text
      "no_overlaps": true,
      "all_sections_enriched": true,
      "thematic_refs_valid": true,
      "word_counts_plausible": true,
      "no_empty_sections": true
    },
    "human_reviewed": false,
    "review_status": "pending",                      // pending|approved|rejected|skipped
    "review_notes": null
  }
}
```

### Schema Rules

1. **`text.content` is immutable.** Once produced, never modify it. Every offset in the entire artifact references this string. Rehash if you must re-clean, but know that all downstream data invalidates.

2. **Section offsets are contiguous.** `sections[n].end_offset == sections[n+1].start_offset` for all adjacent sections. No gaps, no overlaps. The union of all section ranges equals `[0, text.char_count)`.

3. **Section IDs are stable.** `fm_001`, `sec_001`, `bm_001` — front matter, body, back matter. These IDs are referenced by `thematic_index`, `cross_references`, and downstream database records. Don't renumber.

4. **Notable passage offsets are absolute** — they reference `text.content`, not relative to their section.

---

## 2. Project Structure

```
taxonomy-pipeline/
│
├── pyproject.toml                    # Dependencies, project metadata
├── config.yaml                       # Runtime configuration
│
├── prompts/                          # LLM prompt templates (version-controlled)
│   ├── structural_analysis.md        # Stage 3: classify book type
│   ├── boundary_detection.md         # Stage 4: find section breaks
│   ├── section_enrichment.md         # Stage 5: summarize + tag
│   └── book_synthesis.md             # Stage 6: thematic index + routing
│
├── src/
│   ├── __init__.py
│   │
│   ├── schema.py                     # Pydantic models for artifact JSON
│   │
│   ├── llm.py                        # Ollama client (one module, not a package)
│   │
│   ├── pipeline1/
│   │   ├── __init__.py
│   │   ├── runner.py                 # Orchestrator: run stages, checkpoint, resume
│   │   ├── s1_extraction.py          # PDF → raw text
│   │   ├── s2_cleaning.py            # Raw text → clean text (frozen)
│   │   ├── s3_structure.py           # Clean text → book type classification
│   │   ├── s4_boundaries.py          # Clean text + structure → section list
│   │   ├── s5_enrichment.py          # Per-section → summaries, themes, passages
│   │   ├── s6_synthesis.py           # All enrichments → thematic index, routing
│   │   └── s7_validation.py          # Full artifact → confidence score, flags
│   │
│   ├── pipeline2/
│   │   ├── __init__.py
│   │   ├── runner.py                 # Orchestrator
│   │   ├── s1_ingestion.py           # Artifact → Supabase records
│   │   ├── s2_rendering.py           # Clean text + sections → renderable HTML
│   │   ├── s3_navigation.py          # Sections → sidebar tree
│   │   └── s4_routing.py             # Thematic index + hints → queryable data
│   │
│   └── cli.py                        # Entry point: `python -m src.cli`
│
├── data/
│   ├── pdfs/                         # Input: raw PDFs (552 files)
│   ├── artifacts/                    # Output: canonical JSON per book
│   ├── checkpoints/                  # Per-book stage completion markers
│   └── flagged/                      # Books that failed validation (symlinks to artifacts)
│
└── tests/
    ├── conftest.py                   # Shared fixtures
    ├── test_extraction.py
    ├── test_cleaning.py
    ├── test_boundaries.py
    ├── test_validation.py
    ├── test_schema.py                # Artifact schema validation tests
    └── fixtures/
        ├── sample_meditations.pdf    # 5 known test PDFs
        ├── sample_1984.pdf
        ├── sample_republic.pdf
        ├── sample_poetry.pdf         # Edge case: poetry collection
        └── sample_dialogues.pdf      # Edge case: dialogue format
```

---

## 3. Configuration

```yaml
# config.yaml

llm:
  provider: ollama
  base_url: http://localhost:11434
  model: llama3.1:8b
  temperature: 0.3                     # Low temp for structured extraction
  request_timeout: 120                 # Seconds — long for big sections

pipeline1:
  pdf_dir: ./data/pdfs
  artifact_dir: ./data/artifacts
  checkpoint_dir: ./data/checkpoints
  flagged_dir: ./data/flagged

  extraction:
    min_quality_threshold: 0.3         # Below this = skip as garbage
    ocr_detection_threshold: 0.5       # Gibberish ratio above this = suspected OCR

  cleaning:
    header_repeat_threshold: 0.5       # Strip if appears on >50% of pages
    page_number_proximity: 20          # Chars from page boundary to count as page number

  boundaries:
    chunk_size_tokens: 8000            # Sliding window for LLM
    chunk_overlap_tokens: 500          # Overlap between windows

  enrichment:
    max_themes_per_section: 7
    max_passages_per_section: 3

  validation:
    min_confidence: 0.7                # Below this → flagged
    max_gap_chars: 100                 # Allowable gap between sections

  batch:
    concurrency: 1                     # Sequential for local LLM (no parallelism)
    checkpoint_every: 1                # Checkpoint after each stage per book
    retry_on_failure: 2                # Retry failed LLM calls this many times

pipeline2:
  supabase_url: ${SUPABASE_URL}
  supabase_key: ${SUPABASE_SERVICE_KEY}

  rendering:
    strategy: on_demand                # on_demand | prerender
```

---

## 4. Pipeline 1 — Module Design

### Core Abstraction: Stage Results

Each stage produces a typed result. The runner chains them.

```python
# src/schema.py (key types — abbreviated)

from pydantic import BaseModel
from typing import Optional
from enum import Enum

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

# ─── Stage Results ───

class ExtractionResult(BaseModel):
    raw_text: str
    page_count: int
    page_boundaries: list[int]         # char offsets where pages break
    has_toc: bool
    toc_entries: list[dict]            # [{title, page_num}]
    is_ocr: bool
    extraction_quality: float

class CleaningResult(BaseModel):
    clean_text: str
    char_count: int
    word_count: int
    cleaning_log: list[str]
    content_hash: str                  # SHA-256 — THE immutable reference

class StructureResult(BaseModel):
    book_type: BookType
    structure_pattern: str
    hierarchy_levels: int
    has_front_matter: bool
    front_matter_types: list[str]
    has_back_matter: bool
    back_matter_types: list[str]
    confidence: float

class SectionBoundary(BaseModel):
    id: str
    level: int
    type: SectionType
    subtype: str
    title: str
    start_offset: int
    end_offset: int

class NotablePassage(BaseModel):
    text: str
    start_offset: int
    end_offset: int
    significance: str

class SectionEnrichment(BaseModel):
    section_id: str
    summary: str
    key_themes: list[str]
    notable_passages: list[NotablePassage]
    difficulty: Difficulty
    word_count: int
    reading_time_minutes: float

class BookSynthesis(BaseModel):
    domain: str
    subdomains: list[str]
    thematic_index: dict[str, list[str]]     # theme → [section_id]
    routing_hints: dict                       # good_for, not_good_for, pairs_well_with
    cross_references: list[dict]

class ValidationResult(BaseModel):
    confidence: float
    flags: list[str]
    checks: dict[str, bool]
    passed: bool

# ─── The Full Artifact ───

class CanonicalArtifact(BaseModel):
    artifact_version: str
    book_id: str
    generated_at: str
    pipeline_version: str
    source: dict
    text: dict
    structure: StructureResult
    sections: list[dict]               # SectionBoundary + SectionEnrichment merged
    synthesis: BookSynthesis
    quality: dict
```

### Runner: Checkpoint + Resume

```python
# src/pipeline1/runner.py — conceptual design

STAGES = [
    ("s1_extraction", s1_extraction.run),
    ("s2_cleaning",   s2_cleaning.run),
    ("s3_structure",  s3_structure.run),
    ("s4_boundaries", s4_boundaries.run),
    ("s5_enrichment", s5_enrichment.run),
    ("s6_synthesis",  s6_synthesis.run),
    ("s7_validation", s7_validation.run),
]

def process_book(pdf_path: Path, config: Config) -> CanonicalArtifact:
    book_id = derive_book_id(pdf_path)
    checkpoint_dir = config.checkpoint_dir / book_id

    context = {}  # Accumulates stage results

    for stage_name, stage_fn in STAGES:
        checkpoint_file = checkpoint_dir / f"{stage_name}.json"

        if checkpoint_file.exists():
            # Resume: load cached result
            context[stage_name] = load_checkpoint(checkpoint_file)
            continue

        # Run stage, passing all prior context
        result = stage_fn(pdf_path=pdf_path, context=context, config=config)
        context[stage_name] = result

        # Save checkpoint
        save_checkpoint(checkpoint_file, result)

    return assemble_artifact(book_id, context)


def process_batch(config: Config):
    """Process all PDFs in pdf_dir. Skip already-completed books."""
    pdf_dir = Path(config.pipeline1.pdf_dir)

    for pdf_path in sorted(pdf_dir.glob("*.pdf")):
        book_id = derive_book_id(pdf_path)
        artifact_path = config.artifact_dir / f"{book_id}.json"

        if artifact_path.exists():
            continue  # Already done

        try:
            artifact = process_book(pdf_path, config)
            save_artifact(artifact_path, artifact)

            if artifact.quality["confidence"] < config.pipeline1.validation.min_confidence:
                symlink_to_flagged(artifact_path, config.flagged_dir)

        except Exception as e:
            log_failure(book_id, e)
            continue  # Don't let one book kill the batch
```

### Stage Contracts

Each stage function has the same signature:

```python
def run(pdf_path: Path, context: dict, config: Config) -> StageResult:
    """
    pdf_path: original PDF (only Stage 1 reads it directly)
    context:  dict of previous stage results, keyed by stage name
    config:   full config object
    returns:  typed Pydantic model (serializable for checkpointing)
    """
```

Stages reference prior results via `context`:

| Stage | Reads from context | Produces |
|-------|-------------------|----------|
| S1 Extraction | — | `ExtractionResult` |
| S2 Cleaning | `s1_extraction` (raw_text, page_boundaries) | `CleaningResult` |
| S3 Structure | `s2_cleaning` (clean_text, first ~4K tokens) | `StructureResult` |
| S4 Boundaries | `s2_cleaning` (clean_text), `s3_structure`, `s1_extraction` (toc) | `list[SectionBoundary]` |
| S5 Enrichment | `s2_cleaning` (clean_text), `s4_boundaries` (sections) | `list[SectionEnrichment]` |
| S6 Synthesis | `s5_enrichment` (all summaries + themes) | `BookSynthesis` |
| S7 Validation | all prior stages | `ValidationResult` |

---

## 5. Pipeline 1 — Stage Implementation Notes

### S1: Extraction (PyMuPDF, no LLM)

```python
import fitz  # PyMuPDF

def run(pdf_path, context, config):
    doc = fitz.open(str(pdf_path))
    raw_text = ""
    page_boundaries = []

    for page in doc:
        page_boundaries.append(len(raw_text))
        raw_text += page.get_text("text")
        raw_text += "\n\n"  # Page separator

    toc = doc.get_toc()  # [[level, title, page_num], ...]
    toc_entries = [{"title": t[1], "page_num": t[2]} for t in toc]

    # OCR detection heuristic
    avg_char_density = len(raw_text) / max(doc.page_count, 1) / 1000
    gibberish_ratio = count_gibberish_chars(raw_text) / max(len(raw_text), 1)
    is_ocr = gibberish_ratio > config.pipeline1.extraction.ocr_detection_threshold

    return ExtractionResult(
        raw_text=raw_text,
        page_count=doc.page_count,
        page_boundaries=page_boundaries,
        has_toc=len(toc_entries) > 0,
        toc_entries=toc_entries,
        is_ocr=is_ocr,
        extraction_quality=1.0 - gibberish_ratio
    )
```

### S2: Cleaning (deterministic + edge-case LLM)

The cleaning pipeline runs as a sequence of deterministic transformations. Order matters.

```python
def run(pdf_path, context, config):
    extraction = context["s1_extraction"]
    text = extraction.raw_text
    log = []

    # 1. Strip repeating headers/footers
    text, stripped = strip_repeating_headers(text, extraction.page_boundaries, config)
    if stripped: log.append(f"stripped_header: '{stripped}' from pages")

    # 2. Strip page numbers at boundaries
    text, count = strip_page_numbers(text, extraction.page_boundaries)
    if count: log.append(f"stripped_page_numbers: {count} instances")

    # 3. Rejoin hyphenated words at line breaks
    text, count = rejoin_hyphenation(text)
    if count: log.append(f"rejoined_hyphenation: {count} instances")

    # 4. Normalize whitespace
    text, count = normalize_whitespace(text)
    if count: log.append(f"normalized_whitespace: {count} excess newlines removed")

    # 5. Normalize encoding (ligatures, smart quotes)
    text, count = normalize_encoding(text)
    if count: log.append(f"normalized_encoding: {count} characters")

    content_hash = hashlib.sha256(text.encode()).hexdigest()

    return CleaningResult(
        clean_text=text,
        char_count=len(text),
        word_count=len(text.split()),
        cleaning_log=log,
        content_hash=content_hash
    )
```

Key helper functions needed:

- `strip_repeating_headers(text, page_boundaries, config)` — compare first/last N chars of each page, strip if >50% match
- `strip_page_numbers(text, page_boundaries)` — bare numbers within 20 chars of a page boundary
- `rejoin_hyphenation(text)` — match `\w+-\n\w+` patterns, rejoin if the combined word is valid (dictionary check or heuristic)
- `normalize_whitespace(text)` — collapse 3+ newlines to 2, strip tabs/form feeds
- `normalize_encoding(text)` — `ﬁ→fi`, `ﬂ→fl`, smart quotes to straight, em dash normalization

### S3: Structure (LLM — 1 call)

Send the first ~4K tokens of clean text + any TOC data.

Prompt template (`prompts/structural_analysis.md`):
```
You are analyzing the opening of a book to classify its structure.

Here is the beginning of the text:
---
{first_4k_tokens}
---

{toc_section}

Respond in JSON only. No explanation.

{
  "book_type": "treatise|novel|dialogue|collection|manual|poetry|religious|essays",
  "structure_pattern": "describe the hierarchy, e.g. 'parts > chapters' or 'books > entries'",
  "hierarchy_levels": 1-3,
  "has_front_matter": true/false,
  "front_matter_types": ["introduction", "preface", etc],
  "has_back_matter": true/false,
  "back_matter_types": ["endnotes", "index", etc],
  "confidence": 0.0-1.0
}
```

### S4: Boundaries (LLM — sliding window, most critical stage)

This stage sends overlapping ~8K token windows through the LLM. Each window returns any section boundaries found in that chunk.

```
┌─────────────────────────────────────────────────────┐
│  Window 1: chars 0-32000                            │
│              ├── boundary at char 0: "Introduction"  │
│              ├── boundary at char 3847: "Book 1"     │
│              └── boundary at char 12340: "Book 2"    │
│                                                      │
│  Window 2: chars 30000-62000  (overlap: 2000 chars)  │
│              └── boundary at char 45200: "Book 3"    │
│                                                      │
│  Window 3: chars 60000-92000                         │
│              ├── boundary at char 78100: "Book 4"    │
│              └── boundary at char 89000: "Book 5"    │
└─────────────────────────────────────────────────────┘
```

After all windows processed:
1. Deduplicate boundaries found in overlap regions (same title within 200 chars = duplicate)
2. Sort by start_offset
3. Compute end_offsets: each section ends where next begins, last ends at `char_count`
4. Assign IDs: `fm_001`, `sec_001`, `bm_001` based on type

The prompt must be **type-aware** — it receives the `StructureResult` from S3:

```
You are identifying section boundaries in a {book_type} that follows
the pattern: {structure_pattern}.

You should look for {hierarchy_levels} levels of structure.
{front_matter_instruction}
{back_matter_instruction}

Here is a chunk of the text. The chunk starts at character offset {chunk_start}.
For each section boundary you find, report its character offset RELATIVE TO THE CHUNK START.
I will add {chunk_start} to get the absolute offset.

---
{chunk_text}
---

Respond in JSON. Array of boundaries found in this chunk:
[
  {"title": "...", "level": 1, "type": "body", "subtype": "chapter", "offset_in_chunk": N}
]

Return [] if no boundaries in this chunk.
```

### S5: Enrichment (LLM — 1 call per section)

For each section, extract the text slice and send it:

```python
for section in boundaries:
    section_text = clean_text[section.start_offset:section.end_offset]
    enrichment = llm_enrich_section(section_text, section, config)
```

Prompt template:
```
You are analyzing a section of a {book_type}.

Section: "{section_title}" ({section_subtype})
---
{section_text}
---

Respond in JSON:
{
  "summary": "2-3 sentences: what this section IS about, not what it says",
  "key_themes": ["theme1", "theme2", ...],   // 3-7 themes, lowercase, underscored
  "notable_passages": [
    {
      "text": "exact quote from the text",
      "offset_in_section": N,    // char offset within this section's text
      "significance": "why this passage matters"
    }
  ],
  "difficulty": "accessible|moderate|challenging"
}
```

After LLM returns, convert `offset_in_section` to absolute offset: `section.start_offset + offset_in_section`.

### S6: Synthesis (LLM — 1 call per book)

Input is all section enrichments compressed — summaries + themes only, not full text:

```
Here are all sections of "{book_title}" by {author}, a {book_type}:

{for each section:}
  [{section_id}] "{section_title}": {summary}
  Themes: {key_themes}
{end for}

Produce a book-level analysis. Respond in JSON:
{
  "domain": "...",
  "subdomains": ["...", "..."],
  "thematic_index": {
    "theme_name": ["sec_id", "sec_id"],
    ...
  },
  "routing_hints": {
    "good_for": ["human-readable scenario 1", "scenario 2", ...],
    "not_good_for": ["scenario 1", ...],
    "pairs_well_with": ["Book Title — Author", ...]
  },
  "cross_references": [
    {"from_section": "sec_id", "to_section": "sec_id", "relationship": "elaborates|contrasts|extends", "note": "..."}
  ]
}
```

### S7: Validation (no LLM)

Pure checks, produces a confidence score:

```python
def run(pdf_path, context, config):
    checks = {}
    flags = []

    boundaries = context["s4_boundaries"]
    enrichments = context["s5_enrichment"]
    synthesis = context["s6_synthesis"]
    text = context["s2_cleaning"]

    # Check 1: Offsets cover full text
    covered = sum(s.end_offset - s.start_offset for s in boundaries)
    gap = text.char_count - covered
    checks["offsets_complete"] = gap <= config.pipeline1.validation.max_gap_chars
    if not checks["offsets_complete"]:
        flags.append(f"offset_gap:{gap}_chars")

    # Check 2: No overlaps
    sorted_sections = sorted(boundaries, key=lambda s: s.start_offset)
    overlaps = any(
        sorted_sections[i].end_offset > sorted_sections[i+1].start_offset
        for i in range(len(sorted_sections) - 1)
    )
    checks["no_overlaps"] = not overlaps
    if overlaps: flags.append("section_overlap")

    # Check 3: All sections enriched
    enriched_ids = {e.section_id for e in enrichments}
    section_ids = {s.id for s in boundaries}
    checks["all_sections_enriched"] = enriched_ids == section_ids
    if not checks["all_sections_enriched"]:
        flags.append(f"missing_enrichment:{section_ids - enriched_ids}")

    # Check 4: Thematic index refs valid
    all_refs = set()
    for ids in synthesis.thematic_index.values():
        all_refs.update(ids)
    checks["thematic_refs_valid"] = all_refs.issubset(section_ids)
    if not checks["thematic_refs_valid"]:
        flags.append(f"invalid_theme_refs:{all_refs - section_ids}")

    # Check 5: Word counts plausible
    checks["word_counts_plausible"] = all(
        0 < e.word_count < 100000 for e in enrichments
    )

    # Check 6: No empty sections
    checks["no_empty_sections"] = all(
        s.end_offset - s.start_offset > 0 for s in boundaries
    )

    # Composite confidence
    passed_count = sum(checks.values())
    total_checks = len(checks)
    confidence = passed_count / total_checks

    return ValidationResult(
        confidence=confidence,
        flags=flags,
        checks=checks,
        passed=confidence >= config.pipeline1.validation.min_confidence
    )
```

---

## 6. Pipeline 2 — Module Design

### S1: Ingestion (Artifact → Supabase)

```python
def run(artifact: CanonicalArtifact, supabase_client):
    """Upsert one artifact into all required tables."""

    # 1. books table
    supabase_client.table("books").upsert({
        "id": artifact.book_id,
        "title": extract_title(artifact.book_id),
        "author": extract_author(artifact.book_id),
        "domain": artifact.synthesis.domain,
        "subdomains": artifact.synthesis.subdomains,
        "book_type": artifact.structure.book_type,
        "page_count": artifact.source["page_count"],
        "word_count": artifact.text["word_count"],
        "difficulty": compute_overall_difficulty(artifact.sections),
        "routing_hints": artifact.synthesis.routing_hints,
        "thematic_index": artifact.synthesis.thematic_index,
        "artifact_version": artifact.artifact_version,
        "confidence": artifact.quality["confidence"],
    }).execute()

    # 2. book_text table (single source of truth for all text operations)
    supabase_client.table("book_text").upsert({
        "book_id": artifact.book_id,
        "content": artifact.text["content"],
        "content_hash": artifact.text["content_hash"],
    }).execute()

    # 3. chapters/sections table
    for section in artifact.sections:
        supabase_client.table("sections").upsert({
            "id": section["id"],
            "book_id": artifact.book_id,
            "level": section["level"],
            "type": section["type"],
            "subtype": section["subtype"],
            "title": section["title"],
            "start_offset": section["start_offset"],
            "end_offset": section["end_offset"],
            "word_count": section.get("word_count"),
            "reading_time_minutes": section.get("reading_time_minutes"),
            "summary": section.get("summary"),
            "key_themes": section.get("key_themes"),
            "difficulty": section.get("difficulty"),
            "notable_passages": section.get("notable_passages"),
        }).execute()
```

### S2: Rendering (on-demand, not pre-stored)

```python
def render_section_html(clean_text: str, section: dict) -> str:
    """Called at serve-time, not ingestion-time."""
    section_text = clean_text[section["start_offset"]:section["end_offset"]]
    paragraphs = section_text.split("\n\n")

    html_parts = []
    current_offset = section["start_offset"]

    for para in paragraphs:
        para = para.strip()
        if not para:
            current_offset += 2  # skip the \n\n
            continue

        # Detect headers (simple heuristic — short line, possibly all caps or numbered)
        if is_section_header(para, section):
            tag = f'<h2 data-offset="{current_offset}">{escape(para)}</h2>'
        elif is_block_quote(para):
            tag = f'<blockquote data-offset="{current_offset}">{escape(para)}</blockquote>'
        else:
            tag = f'<p data-offset="{current_offset}">{escape(para)}</p>'

        html_parts.append(tag)
        current_offset += len(para) + 2  # +2 for the \n\n separator

    return "\n".join(html_parts)
```

The `data-offset` attribute is critical — it's how highlights and annotations anchor to the text. It survives page reloads.

### S3: Navigation (pure transformation)

```python
def build_nav_tree(sections: list[dict]) -> list[dict]:
    """Sections → nested sidebar structure."""
    tree = []
    stack = [{"children": tree, "level": -1}]

    for section in sections:
        node = {
            "id": section["id"],
            "title": section["title"],
            "level": section["level"],
            "type": section["type"],
            "subtype": section.get("subtype"),
            "word_count": section.get("word_count"),
            "reading_time_minutes": section.get("reading_time_minutes"),
            "children": []
        }

        # Walk back up the stack to find the right parent
        while stack[-1]["level"] >= section["level"]:
            stack.pop()

        stack[-1]["children"].append(node)
        stack.append(node)

    return tree
```

### S4: Routing Data (query layer)

Two query paths, neither requires an LLM:

```python
# Path 1: Theme lookup
def find_sections_by_themes(themes: list[str], supabase_client) -> list[dict]:
    """Given themes from intent classifier, find matching sections."""
    results = supabase_client.rpc("match_themes", {"input_themes": themes}).execute()
    return results.data

# SQL function (in Supabase):
# CREATE OR REPLACE FUNCTION match_themes(input_themes text[])
# RETURNS TABLE(book_id text, section_id text, theme text, book_title text, section_title text)
# AS $$
#   SELECT b.id, t.section_id, t.theme, b.title, s.title
#   FROM thematic_index t
#   JOIN books b ON b.id = t.book_id
#   JOIN sections s ON s.id = t.section_id
#   WHERE t.theme = ANY(input_themes)
# $$ LANGUAGE sql;

# Path 2: Routing hint scan
def find_books_by_scenario(user_query: str, supabase_client) -> list[dict]:
    """Fuzzy match user query against good_for arrays."""
    books = supabase_client.table("books").select("id, title, routing_hints").execute()
    scored = []
    for book in books.data:
        hints = book["routing_hints"]["good_for"]
        score = max(fuzzy_match(user_query, hint) for hint in hints)
        if score > 0.4:
            scored.append({"book": book, "score": score})
    return sorted(scored, key=lambda x: -x["score"])
```

Then the **Reading Router LLM** receives pre-filtered candidates (not the full corpus) and selects 2-4 reading paths.

---

## 7. LLM Client

One thin wrapper. Everything goes through here.

```python
# src/llm.py

import httpx
import json

class OllamaClient:
    def __init__(self, base_url: str, model: str, temperature: float, timeout: int):
        self.base_url = base_url
        self.model = model
        self.temperature = temperature
        self.timeout = timeout

    def generate_json(self, prompt: str, system: str = None) -> dict:
        """Send prompt, expect JSON response, parse and return."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = httpx.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": self.temperature},
                "format": "json"       # Ollama's JSON mode
            },
            timeout=self.timeout
        )
        response.raise_for_status()

        content = response.json()["message"]["content"]
        return json.loads(content)

    def generate_text(self, prompt: str, system: str = None) -> str:
        """For non-structured responses."""
        # Same as above but without format: json
        ...
```

Key decisions:
- **`format: "json"` in Ollama** — forces JSON output, reduces parsing failures
- **No streaming** — we need complete responses for JSON parsing
- **Retry with backoff** — wrap calls in retry logic (LLM can occasionally fail or timeout)
- **Temperature 0.3** — low for structural extraction, could go lower for boundaries

---

## 8. Checkpoint System

```
data/checkpoints/
  meditations__marcus_aurelius/
    s1_extraction.json       # 34KB — raw text + metadata
    s2_cleaning.json         # 30KB — clean text + log
    s3_structure.json        # 1KB  — classification
    s4_boundaries.json       # 3KB  — section list
    s5_enrichment.json       # 8KB  — all enrichments
    s6_synthesis.json        # 4KB  — thematic index + routing
    s7_validation.json       # 1KB  — checks + score
```

Rules:
- Each file is the serialized Pydantic model for that stage
- If a checkpoint exists, skip the stage on re-run
- If you need to re-run a stage, delete that checkpoint AND all subsequent ones
  (because later stages depend on earlier ones)
- The runner handles this: `--rerun-from s4` deletes s4/s5/s6/s7 checkpoints

---

## 9. CLI Interface

```bash
# Process a single book (for testing)
python -m src.cli process --pdf data/pdfs/meditations.pdf

# Process all PDFs in batch
python -m src.cli batch --pdf-dir data/pdfs/

# Resume a failed batch (skips completed books)
python -m src.cli batch --pdf-dir data/pdfs/ --resume

# Re-run from a specific stage for one book
python -m src.cli process --pdf data/pdfs/meditations.pdf --rerun-from s4_boundaries

# Validate all artifacts
python -m src.cli validate --artifact-dir data/artifacts/

# List flagged books
python -m src.cli flagged --artifact-dir data/artifacts/

# Pipeline 2: ingest artifacts into Supabase
python -m src.cli ingest --artifact-dir data/artifacts/

# Pipeline 2: ingest a single artifact
python -m src.cli ingest --artifact data/artifacts/meditations__marcus_aurelius.json

# Verify ingested books (Pipeline 2, Stage 5)
python -m src.cli verify --book-id meditations__marcus_aurelius
```

---

## 10. Dependencies

```toml
# pyproject.toml

[project]
name = "taxonomy-pipeline"
requires-python = ">=3.11"
dependencies = [
    "pymupdf>=1.24",           # PDF text extraction
    "pydantic>=2.0",           # Schema validation
    "httpx>=0.27",             # HTTP client (for Ollama API)
    "pyyaml>=6.0",             # Config loading
    "click>=8.0",              # CLI framework
    "supabase>=2.0",           # Supabase Python client (Pipeline 2)
    "rich>=13.0",              # CLI progress bars and tables
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio",
]
```

---

## 11. Database Schema Additions (Supabase)

Pipeline 2 needs these tables/columns beyond what may already exist:

```sql
-- Sections table (may need renaming from 'chapters')
CREATE TABLE IF NOT EXISTS sections (
    id TEXT PRIMARY KEY,                          -- "sec_001", "fm_001"
    book_id TEXT REFERENCES books(id),
    level INTEGER NOT NULL,
    type TEXT NOT NULL,                            -- front_matter, body, back_matter
    subtype TEXT,                                  -- chapter, introduction, etc
    title TEXT NOT NULL,
    start_offset INTEGER NOT NULL,
    end_offset INTEGER NOT NULL,
    word_count INTEGER,
    reading_time_minutes REAL,
    summary TEXT,
    key_themes JSONB,                             -- ["theme1", "theme2"]
    notable_passages JSONB,                       -- [{text, start_offset, end_offset, significance}]
    difficulty TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_sections_book ON sections(book_id);
CREATE INDEX idx_sections_themes ON sections USING GIN(key_themes);

-- Add columns to books table if not present
ALTER TABLE books ADD COLUMN IF NOT EXISTS domain TEXT;
ALTER TABLE books ADD COLUMN IF NOT EXISTS subdomains JSONB;
ALTER TABLE books ADD COLUMN IF NOT EXISTS book_type TEXT;
ALTER TABLE books ADD COLUMN IF NOT EXISTS routing_hints JSONB;
ALTER TABLE books ADD COLUMN IF NOT EXISTS thematic_index JSONB;
ALTER TABLE books ADD COLUMN IF NOT EXISTS confidence REAL;
ALTER TABLE books ADD COLUMN IF NOT EXISTS artifact_version TEXT;
```

---

## 12. Error Taxonomy

What can fail and what to do about it:

| Failure | Detection | Recovery |
|---------|-----------|----------|
| PDF extraction returns <100 chars | S1: char count check | Flag as garbage, skip |
| LLM returns invalid JSON | S3-S6: JSON parse failure | Retry up to 2x, then flag |
| LLM hallucinates section boundaries | S7: offset gap check | Flag for human review |
| Section boundaries overlap | S7: overlap check | Flag, attempt auto-merge |
| Enrichment summary is empty/generic | S7: summary quality heuristic | Re-run S5 for that section |
| Ollama process dies | Stage runner: connection error | Log, checkpoint saved, resume later |
| Thematic index references missing sections | S7: ref validation | Strip invalid refs, flag |
| Book is poetry with no clear sections | S4: zero boundaries returned | Use single-section fallback |

---

## 13. Testing Strategy

**5 Test Books** — chosen to cover the structural spectrum:

| Book | Type | Structure | Why It's a Test Case |
|------|------|-----------|---------------------|
| Meditations — Marcus Aurelius | Treatise | Books > entries | Well-structured, numbered sections |
| 1984 — George Orwell | Novel | Parts > chapters | Standard fiction structure |
| The Republic — Plato | Dialogue | Books (continuous) | Dialogue format, no clear paragraphs |
| Leaves of Grass — Whitman | Poetry | Sections > poems | Poetry line breaks, no chapters |
| The Art of War — Sun Tzu | Manual | Chapters > passages | Short chapters, aphoristic style |

For each test book, verify:
1. Clean text reads like the book, not a PDF dump
2. Section boundaries match the real table of contents
3. Summaries accurately describe section content
4. Themes are relevant and useful for routing
5. Routing hints make sense for real user queries
6. Full artifact passes validation with confidence > 0.8