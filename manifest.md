Let me first understand what currently exists in your repository before I lay out the architecture.

[7 tools called]

Now let me dig into what's been extracted and the existing app structure.

[2 tools called]

Let me look at a couple of extracted files to understand the current quality level.

[4 tools called]

Now I have the full picture. Here's my analysis.

---

## The Honest Assessment

You have **552 PDFs**, of which **518 extracted** into JSON. But the extraction quality is bad enough to be the foundational bottleneck of everything you want to build. Here are the cold numbers:

- **183 books** (35%) have exactly **1 chapter** (fallback = "Full Text" = no structure at all)
- **70 books** have 2-5 chapters (many of these are regex false positives)
- The chapter detection is **regex-first** and produces garbage like `"C: . the"` as a chapter title (Meditations example above)
- Roman numeral regex is matching in-text citations, footnotes, and date ranges as "chapters"
- Only **31 out of 518** were actually ingested into Supabase

The current extraction pipeline is a blunt instrument. Regex for chapter detection across 500+ books spanning philosophy, fiction, technical manuals, and religious texts will never work. Each book has its own structural DNA. This is exactly the right problem for local LLMs.

---

## The Architecture: Taxonomy Engine via Local LLM Parsing

Here's what I'd propose. This is the full system diagram, the why, and the sequencing.

### The Problem (One Sentence)

You need to transform 500+ raw PDFs into a **structured, navigable, semantically-tagged knowledge base** where every section is addressable, searchable, and contextually meaningful — and you need to do this **once, correctly**.

### Eagle View: The Whole System

```
┌─────────────────────────────────────────────────────────────────────┐
│                    TAXONOMY ENGINE (OFFLINE, LOCAL)                 │
│                                                                     │
│  ┌──────────┐    ┌──────────────┐    ┌───────────────┐             │
│  │ Raw PDF  │───►│ Text Extract │───►│ Structure LLM │             │
│  │ (552)    │    │ (PyMuPDF)    │    │ (Local, e.g.  │             │
│  └──────────┘    └──────────────┘    │ Llama 3/Qwen) │             │
│                                      └───────┬───────┘             │
│                                              │                     │
│                           ┌──────────────────┼──────────────┐      │
│                           ▼                  ▼              ▼      │
│                  ┌──────────────┐  ┌──────────────┐ ┌───────────┐  │
│                  │ Book         │  │ Section      │ │ Sectional │  │
│                  │ Taxonomy     │  │ Boundaries   │ │ Insights  │  │
│                  │ (metadata)   │  │ (offsets)    │ │ (summaries│  │
│                  └──────┬───────┘  └──────┬───────┘ │ ,themes)  │  │
│                         │                 │         └─────┬─────┘  │
│                         └────────┬────────┘               │        │
│                                  ▼                        │        │
│                     ┌───────────────────────┐             │        │
│                     │   CANONICAL ARTIFACT  │◄────────────┘        │
│                     │   (one JSON per book) │                      │
│                     └───────────┬───────────┘                      │
│                                 │                                  │
└─────────────────────────────────┼──────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    ALEXANDRIA PLATFORM (ONLINE)                     │
│                                                                     │
│  ┌───────────┐    ┌───────────────┐    ┌──────────────────────┐    │
│  │ User asks │───►│ Intent +      │───►│ Reader               │    │
│  │ question  │    │ Router (LLM)  │    │ (renders sections,   │    │
│  └───────────┘    │ uses taxonomy │    │  not raw PDF)        │    │
│                   │ + insights    │    │                      │    │
│                   └───────────────┘    │  - chapter nav       │    │
│                                       │  - highlight         │    │
│                                       │  - section chat      │    │
│                                       │  - annotations       │    │
│                                       └──────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

### The Canonical Artifact: What One Book Becomes

This is the structure the local LLM produces for **each book**. This replaces the current broken JSON.

```json
{
  "id": "book_<hash>",
  "meta": {
    "title": "Meditations",
    "author": "Marcus Aurelius",
    "translator": "Gregory Hays",
    "publication_year": 180,
    "translation_year": 2002,
    "language": "English",
    "original_language": "Koine Greek",
    "domain": "philosophy",
    "subdomains": ["stoicism", "ethics", "self-governance"],
    "difficulty": "accessible",
    "page_count": 307,
    "word_count": 56611
  },

  "structure": {
    "type": "multi_book",
    "hierarchy": ["book", "entry"],
    "has_introduction": true,
    "has_notes": true,
    "has_index": false
  },

  "front_matter": [
    {
      "type": "introduction",
      "title": "Introduction",
      "start_offset": 0,
      "end_offset": 2725,
      "summary": "Hays introduces Marcus Aurelius as Roman emperor and Stoic philosopher, contextualizing the Meditations as private journal entries never intended for publication."
    }
  ],

  "sections": [
    {
      "id": "sec_001",
      "level": 1,
      "type": "book",
      "number": 1,
      "title": "Book 1: Debts and Lessons",
      "start_offset": 2725,
      "end_offset": 12400,
      "word_count": 1800,
      "summary": "Marcus catalogs the virtues and lessons he learned from family, teachers, and mentors — a practice of gratitude and intellectual genealogy.",
      "key_themes": ["gratitude", "mentorship", "character formation"],
      "notable_passages": [
        {
          "offset_start": 2800,
          "offset_end": 2950,
          "text_preview": "From my grandfather Verus I learned good morals and the government of my temper...",
          "significance": "Opening passage establishing the structure of debt to predecessors"
        }
      ],
      "subsections": [
        {
          "id": "sec_001_01",
          "level": 2,
          "type": "entry",
          "title": "From my grandfather Verus",
          "start_offset": 2800,
          "end_offset": 3100
        }
      ],
      "connects_to": ["sec_002", "sec_006"],
      "reading_time_minutes": 8
    }
  ],

  "back_matter": [
    {
      "type": "notes",
      "title": "Notes",
      "start_offset": 300000,
      "end_offset": 328300
    }
  ],

  "thematic_index": {
    "death": ["sec_002", "sec_004", "sec_009", "sec_012"],
    "impermanence": ["sec_002", "sec_004", "sec_006"],
    "duty": ["sec_001", "sec_003", "sec_005", "sec_006"],
    "self-discipline": ["sec_002", "sec_003", "sec_005", "sec_010"],
    "nature": ["sec_002", "sec_004", "sec_007", "sec_009"]
  },

  "routing_hints": {
    "good_for": [
      "dealing with things outside your control",
      "finding purpose in daily obligations",
      "acceptance of mortality",
      "emotional regulation",
      "leadership under pressure"
    ],
    "not_good_for": [
      "systematic philosophy",
      "logical argumentation",
      "epistemology"
    ],
    "pairs_well_with": [
      "Letters from a Stoic - Seneca",
      "Discourses - Epictetus",
      "The Enchiridion - Epictetus"
    ]
  },

  "extraction_meta": {
    "model_used": "llama-3.1-8b-instruct",
    "extraction_date": "2026-02-05T...",
    "confidence": 0.92,
    "human_verified": false,
    "version": 1
  }
}
```

### Why This Structure Solves Your Problems

| Problem | How This Solves It |
|---|---|
| "PDFs on screen" isn't interactable | Sections are individually addressable — render text, not PDF |
| Users can't navigate | `sections` with hierarchy give you chapter/subchapter nav |
| Routing to the right section | `thematic_index` + `routing_hints` + `summary` per section |
| LLM companion needs scope | Each section has clear boundaries (offsets) for context windows |
| Highlighting needs anchoring | Character offsets give stable text positions |
| Search needs semantics | `key_themes`, `summary`, `good_for` enable semantic routing |
| Bad chapter detection | LLM understands "this is an introduction, not chapter 1" |

### The Local LLM Pipeline: How to Actually Do This

```
  ┌──────────────────────────────────────────────────┐
  │           FOR EACH BOOK (batch processing)       │
  │                                                  │
  │  Step 1: Extract raw text                        │
  │  ┌─────────────────────────┐                     │
  │  │ PyMuPDF (fitz)          │                     │
  │  │ - Extract text per page │                     │
  │  │ - Preserve page breaks  │                     │
  │  │ - Get TOC if exists     │                     │
  │  └───────────┬─────────────┘                     │
  │              │                                   │
  │  Step 2: Structural analysis                     │
  │  ┌───────────▼─────────────┐                     │
  │  │ Local LLM Pass 1       │                     │
  │  │ (Sliding window)       │                     │
  │  │                        │                     │
  │  │ Input: First 4K tokens │                     │
  │  │ Prompt: "What type of  │                     │
  │  │  book is this? What is │                     │
  │  │  the structure? Detect │                     │
  │  │  TOC, preface, etc."   │                     │
  │  └───────────┬─────────────┘                     │
  │              │                                   │
  │  Step 3: Section boundary detection              │
  │  ┌───────────▼─────────────┐                     │
  │  │ Local LLM Pass 2       │                     │
  │  │ (Chunked, sequential)  │                     │
  │  │                        │                     │
  │  │ For each ~8K chunk:    │                     │
  │  │ "Given this is a       │                     │
  │  │  [philosophy] book     │                     │
  │  │  with [book/entry]     │                     │
  │  │  structure, identify   │                     │
  │  │  section boundaries    │                     │
  │  │  in this text."        │                     │
  │  └───────────┬─────────────┘                     │
  │              │                                   │
  │  Step 4: Section-level enrichment                │
  │  ┌───────────▼─────────────┐                     │
  │  │ Local LLM Pass 3       │                     │
  │  │ (Per section)          │                     │
  │  │                        │                     │
  │  │ For each section:      │                     │
  │  │ - Summary (2-3 lines)  │                     │
  │  │ - Key themes (tags)    │                     │
  │  │ - Notable passages     │                     │
  │  │ - Difficulty level     │                     │
  │  │ - Reading time         │                     │
  │  └───────────┬─────────────┘                     │
  │              │                                   │
  │  Step 5: Book-level synthesis                    │
  │  ┌───────────▼─────────────┐                     │
  │  │ Local LLM Pass 4       │                     │
  │  │ (Whole book context)   │                     │
  │  │                        │                     │
  │  │ Given all sections:    │                     │
  │  │ - Thematic index       │                     │
  │  │ - Routing hints        │                     │
  │  │ - Cross-section links  │                     │
  │  │ - "Pairs well with"    │                     │
  │  └───────────┬─────────────┘                     │
  │              │                                   │
  │  Step 6: Validate + Write artifact               │
  │  ┌───────────▼─────────────┐                     │
  │  │ Validation             │                     │
  │  │ - Offsets align?       │                     │
  │  │ - Coverage = 100%?     │                     │
  │  │ - No overlapping secs? │                     │
  │  │ - Themes non-empty?    │                     │
  │  │                        │                     │
  │  │ Output: book.json      │                     │
  │  │ Flag if low confidence │                     │
  │  └────────────────────────┘                      │
  │                                                  │
  └──────────────────────────────────────────────────┘
```

### Model Selection for Local LLM

What you need running on your Mac:

- **Llama 3.1 8B Instruct** (Q4 quantized) — fits in ~6GB VRAM, good structural reasoning
- **Qwen 2.5 7B** — strong at structured output / JSON, good alternative
- Served via **Ollama** or **llama.cpp** locally — no API costs, no rate limits, runs overnight

For 500+ books with 4 passes each, you're looking at:
- ~2000 LLM calls
- At ~30 seconds per call on M-series Mac = ~17 hours unattended
- Fully parallelizable if you batch intelligently (multiple Ollama instances)

### The Reader: How This Becomes Interactable

The current app serves raw PDF via `/library/<id>/view`. That's a dead end. With the taxonomy artifacts, the reader becomes:

```
┌─────────────────────────────────────────────────────────┐
│  READER VIEW                                            │
│                                                         │
│  ┌───────────────┐  ┌──────────────────────────────┐   │
│  │ CHAPTER NAV   │  │ SECTION CONTENT              │   │
│  │               │  │                              │   │
│  │ ▶ Introduction│  │  ┌─ highlighted by user ──┐  │   │
│  │   Book 1 ◄────│  │  │ "From my grandfather   │  │   │
│  │   Book 2      │  │  │  Verus I learned good  │  │   │
│  │   Book 3      │  │  │  morals and the        │  │   │
│  │   Book 4      │  │  │  government of my      │  │   │
│  │   ...         │  │  │  temper."               │  │   │
│  │   Book 12     │  │  └────────────────────────┘  │   │
│  │   Notes       │  │                              │   │
│  │               │  │  The text continues as       │   │
│  └───────────────┘  │  clean, rendered HTML...     │   │
│                     │                              │   │
│  ┌───────────────┐  │                              │   │
│  │ SECTION INFO  │  │                              │   │
│  │               │  │                              │   │
│  │ Themes:       │  │                              │   │
│  │ · gratitude   │  └──────────────────────────────┘   │
│  │ · mentorship  │                                     │
│  │ · character   │  ┌──────────────────────────────┐   │
│  │               │  │ SECTION CHAT                 │   │
│  │ ~8 min read   │  │                              │   │
│  │               │  │ "What does Marcus mean by    │   │
│  │ Also see:     │  │  'government of temper'?"    │   │
│  │ · Book 6      │  │                              │   │
│  │ · Seneca,     │  │ [constrained to this section]│   │
│  │   Letter 6    │  └──────────────────────────────┘   │
│  └───────────────┘                                     │
└─────────────────────────────────────────────────────────┘
```

The content is **rendered text** (HTML), not a PDF embed. The section boundaries from your taxonomy artifact give you:
- Clean chapter navigation
- Scroll-to-section with anchors
- Highlight anchoring via character offsets
- Section-scoped LLM chat (context window = just that section's text)
- Thematic cross-references

### Implementation Sequence

```
PHASE 0: Local LLM Setup (Day 1)
├── Install Ollama
├── Pull Llama 3.1 8B or Qwen 2.5 7B
├── Write a single-book test script
├── Validate output against Meditations manually
└── GATE: One book produces a correct artifact

PHASE 1: Batch Taxonomy Pipeline (Days 2-5)
├── Build the 4-pass pipeline script
├── Run on 10 books, manual review
├── Tune prompts based on failure modes
├── Run on full corpus (~17 hours overnight)
├── Validation pass: flag low-confidence books
└── GATE: 80%+ books have valid artifacts

PHASE 2: Manual Review & Correction (Days 5-7)
├── Review flagged books (low confidence, 1-chapter fallbacks)
├── Fix edge cases (poetry, dialogues, collections)
├── Re-run failed books with adjusted prompts
└── GATE: 95%+ books have valid artifacts

PHASE 3: Reader Integration (Days 7-14)
├── New reader endpoint: renders text from artifact, not PDF
├── Chapter navigation from artifact structure
├── Section-scoped highlighting
├── Section-scoped LLM chat
└── GATE: One book is fully navigable and interactable

PHASE 4: Routing Integration (Days 14-21)
├── Routing uses thematic_index + routing_hints
├── User query → specific sections, not just books
├── "You should read Book 4, entries 3-7 of Meditations"
└── GATE: User query returns section-level results
```

### What This Does NOT Include (Intentionally Deferred)

- Vector embeddings / semantic search (you don't need this yet — thematic index + routing hints get you 80% of the way)
- Cross-book synthesis (your design doc explicitly defers this)
- User-generated taxonomy edits (canon is sacred)
- Automated PDF ingestion for new books (admin process stays manual)

### The Risk Register

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| LLM produces garbage sections | High for some books | Breaks reader | Validation pass + human review queue |
| Character offsets drift after re-extraction | Medium | Highlights break | Lock text extraction; offsets are computed once from locked text |
| 17-hour batch fails midway | Medium | Lost progress | Checkpoint per book; resume from last success |
| Some books resist structure (poetry, aphorisms) | High | No clean sections | Special "collection" type in taxonomy; entries instead of chapters |
| Local LLM too slow on your machine | Low (M-series) | Timeline slips | Reduce to 2 passes; merge structural + enrichment |

---

### Your Key Decision Points

1. **Which local LLM model?** Depends on your Mac's specs (M1/M2/M3, RAM). Llama 3.1 8B Q4 needs ~6GB. Qwen 2.5 7B is slightly better at structured JSON output. Both work.

2. **Store text as HTML or plain text?** I'd go plain text in the artifact, render to HTML at serve time. Keeps the artifact clean, rendering is a presentation concern.

3. **Keep PDF serving as fallback?** Yes. Some users may want the original layout (tables, diagrams, figures). The taxonomy reader is the primary experience; PDF is the "view original" escape hatch.

4. **How to handle multi-version books?** (You have "1984 V1", "1984 V2", etc.) These are likely different PDF qualities of the same book. Pick the best extraction, deduplicate before the taxonomy pass.

This is the once-and-for-all structural investment. The entire platform — routing, reading, highlighting, chat — depends on the quality of these artifacts. Get this right and everything downstream flows. Get it wrong and you're rendering garbage in a pretty UI.

What's your Mac's specs? That determines the model choice and batch timing. And do you want me to lay out the exact prompts for each of the 4 LLM passes?

Here's the full content to populate your notebook. This is organized into the three sections you asked for: Architecture, User Flows, and Features. Everything is grounded in what actually exists, what's broken, and what needs to happen.

---

## NOTEBOOK: SECTION 1 — CURRENT STATE AUDIT

Before architecture or flows, you need a sober picture of where you stand.

### What Exists

```
552 PDFs in batch1books/
518 extracted to JSON (34 failed entirely)
184 JSON files in extracted/ (main output)
 20 JSON files in extracted_test/ (validation set)
 31 actually ingested into Supabase (out of 518)
```

### Extraction Quality (the actual problem)

```
Extraction methods used:
  regex:    351 books  (67%)  — regex pattern matching for chapter headers
  toc:       15 books  ( 3%)  — parsed table of contents
  llm:        0 books  ( 0%)  — never used
  fallback: 151 books  (29%)  — single "Full Text" blob, no structure

Chapter count distribution:
  1 chapter:    183 books (35%)  — USELESS for navigation
  2-5 chapters:  70 books (14%)  — many are false positives
  6-20:         106 books (20%)  — probably correct
  21-50:         77 books (15%)  — probably correct
  51+:           81 books (16%)  — some correct, some regex gone wild
```

### Specific Quality Failures Observed

- **Meditations** (Marcus Aurelius): Has 12 Books in reality. Extraction produced 40+ "chapters" because regex matched `C:` patterns in dates/citations like "280–c. 206" as Roman numeral section markers. Chapter titles are garbage: `"C: . the"`, `"C: .) and Chrysippus"`.
- **1984**: Only 3 chapters detected, missing Book II entirely.
- **A Clockwork Orange**: Chapters have tab characters in titles, offset gaps of 16 characters between "chapters" (false positives).
- **183 books** are a single monolithic blob with no structure at all.

### Verdict

The current extraction is not a foundation. It's a liability. Regex cannot solve structural detection across 500+ books spanning philosophy, fiction, technical manuals, religious texts, poetry, and dialogues. Each genre has its own structural DNA.

---

## NOTEBOOK: SECTION 2 — ARCHITECTURE

### 2.1 The Two Systems

Alexandria is actually **two separate systems** that must be built and thought about independently:

```
SYSTEM A: TAXONOMY ENGINE (Offline, Local, One-Time)
  Purpose: Transform raw PDFs → structured, navigable artifacts
  Runs: On your machine, using local LLMs
  Output: One canonical JSON artifact per book
  Frequency: Once per book, ever. Then frozen.

SYSTEM B: READING PLATFORM (Online, User-Facing)
  Purpose: Route users to sections, render text, enable depth
  Runs: Server (FastAPI + Supabase)
  Input: Consumes the artifacts from System A
  Frequency: Always running
```

These two systems share ZERO code. System A feeds System B via artifacts (JSON files). That's the only interface.

### 2.2 System A: Taxonomy Engine

```
┌─────────────────────────────────────────────────────────────┐
│                 TAXONOMY ENGINE (your machine)               │
│                                                              │
│  INPUT                                                       │
│  ┌──────────┐                                                │
│  │ Raw PDF  │                                                │
│  │ (552)    │                                                │
│  └────┬─────┘                                                │
│       │                                                      │
│  STAGE 1: TEXT EXTRACTION (deterministic, no LLM)            │
│  ┌────▼─────────────────────────────────────┐                │
│  │ PyMuPDF (fitz)                           │                │
│  │  - Extract text per page                 │                │
│  │  - Preserve page boundaries              │                │
│  │  - Extract embedded TOC metadata if any  │                │
│  │  - Compute full-text character offsets    │                │
│  │  - Detect: is this scanned/OCR or native?│                │
│  └────┬─────────────────────────────────────┘                │
│       │                                                      │
│  STAGE 2: STRUCTURAL ANALYSIS (local LLM, per book)         │
│  ┌────▼─────────────────────────────────────┐                │
│  │ LLM Pass 1: "What is this book?"         │                │
│  │  Input: first ~4K tokens + TOC if exists  │                │
│  │  Output:                                  │                │
│  │    - Book type (treatise, novel, dialogue, │                │
│  │      collection, manual, poetry, religious)│                │
│  │    - Structure pattern (parts>chapters,    │                │
│  │      books>entries, sections, continuous)  │                │
│  │    - Has: preface? introduction? notes?    │                │
│  │      appendix? index? bibliography?        │                │
│  └────┬─────────────────────────────────────┘                │
│       │                                                      │
│  STAGE 3: SECTION BOUNDARY DETECTION (local LLM, chunked)   │
│  ┌────▼─────────────────────────────────────┐                │
│  │ LLM Pass 2: "Where are the boundaries?"   │                │
│  │  Input: ~8K token sliding windows          │                │
│  │  Context: book type + structure from Pass 1│                │
│  │  Output: list of section boundaries with:  │                │
│  │    - Level (1=major, 2=sub, 3=sub-sub)    │                │
│  │    - Type (part, chapter, section, entry)  │                │
│  │    - Title (cleaned, as the author wrote)  │                │
│  │    - Character offset (start)              │                │
│  └────┬─────────────────────────────────────┘                │
│       │                                                      │
│  STAGE 4: SECTION ENRICHMENT (local LLM, per section)        │
│  ┌────▼─────────────────────────────────────┐                │
│  │ LLM Pass 3: "What is in this section?"    │                │
│  │  Input: full section text                  │                │
│  │  Output per section:                       │                │
│  │    - Summary (2-3 sentences)               │                │
│  │    - Key themes (3-7 tags)                 │                │
│  │    - Notable passages (1-3 with offsets)   │                │
│  │    - Difficulty level                      │                │
│  │    - Estimated reading time                │                │
│  └────┬─────────────────────────────────────┘                │
│       │                                                      │
│  STAGE 5: BOOK-LEVEL SYNTHESIS (local LLM, once per book)    │
│  ┌────▼─────────────────────────────────────┐                │
│  │ LLM Pass 4: "How does this book fit?"     │                │
│  │  Input: all section summaries + themes     │                │
│  │  Output:                                   │                │
│  │    - Domain / subdomains                   │                │
│  │    - Thematic index (theme → section IDs)  │                │
│  │    - Routing hints (good_for, not_good_for)│                │
│  │    - Cross-references (pairs_well_with)    │                │
│  │    - Overall difficulty                    │                │
│  └────┬─────────────────────────────────────┘                │
│       │                                                      │
│  STAGE 6: VALIDATION + ARTIFACT WRITE                        │
│  ┌────▼─────────────────────────────────────┐                │
│  │ Automated checks:                         │                │
│  │  - Offsets cover 100% of text? (no gaps)  │                │
│  │  - No overlapping sections?               │                │
│  │  - Every section has summary + themes?    │                │
│  │  - Structure type matches detected pattern?│                │
│  │  - Confidence score computed              │                │
│  │                                            │                │
│  │ If confidence < threshold → flag for       │                │
│  │   human review                             │                │
│  │                                            │                │
│  │ Write: artifacts/{book_id}.json            │                │
│  └──────────────────────────────────────────┘                │
│                                                              │
│  OUTPUT                                                      │
│  ┌──────────────────────┐                                    │
│  │ artifacts/            │                                    │
│  │   book_001.json       │  ← canonical, immutable           │
│  │   book_002.json       │                                    │
│  │   ...                 │                                    │
│  │   book_518.json       │                                    │
│  │   _manifest.json      │  ← index of all books + status    │
│  │   _flagged.json       │  ← books needing human review     │
│  └──────────────────────┘                                    │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 2.3 The Canonical Artifact (What One Book Becomes)

This is the single most important data structure in the entire platform. Everything downstream depends on it.

```
{
  "artifact_version": 2,
  "id": "book_<hash>",

  "meta": {
    "title": "Meditations",
    "author": "Marcus Aurelius",
    "translator": "Gregory Hays",
    "original_language": "Koine Greek",
    "publication_year_original": 180,
    "publication_year_edition": 2002,
    "domain": "philosophy",
    "subdomains": ["stoicism", "ethics", "self-governance"],
    "book_type": "collection",
    "difficulty": "accessible",
    "page_count": 307,
    "word_count": 56611,
    "char_count": 328300
  },

  "structure": {
    "pattern": "books > entries",
    "hierarchy_levels": 2,
    "has_front_matter": true,
    "has_back_matter": true,
    "total_sections": 12,
    "total_subsections": 170
  },

  "front_matter": [
    {
      "id": "fm_001",
      "type": "introduction",
      "title": "Introduction",
      "start_offset": 0,
      "end_offset": 2725,
      "word_count": 520,
      "summary": "Gregory Hays contextualizes Marcus Aurelius as ...",
      "is_navigable": true
    }
  ],

  "sections": [
    {
      "id": "sec_001",
      "level": 1,
      "type": "book",
      "number": 1,
      "title": "Book 1: Debts and Lessons",
      "start_offset": 2725,
      "end_offset": 12400,
      "word_count": 1800,
      "reading_time_minutes": 8,
      "summary": "Marcus catalogs virtues learned from family, 
                  teachers, mentors — intellectual genealogy 
                  through gratitude.",
      "key_themes": ["gratitude", "mentorship", "character"],
      "notable_passages": [
        {
          "text_preview": "From my grandfather Verus I learned...",
          "offset_start": 2800,
          "offset_end": 2950,
          "significance": "Opening structure of debt to predecessors"
        }
      ],
      "subsections": [
        {
          "id": "sec_001_01",
          "level": 2,
          "type": "entry",
          "title": "1. From my grandfather Verus",
          "start_offset": 2800,
          "end_offset": 3100
        }
      ],
      "connects_to": ["sec_002", "sec_006"]
    }
  ],

  "back_matter": [
    {
      "id": "bm_001",
      "type": "notes",
      "title": "Notes",
      "start_offset": 300000,
      "end_offset": 328300,
      "is_navigable": false
    }
  ],

  "thematic_index": {
    "death_and_impermanence": ["sec_002", "sec_004", "sec_009"],
    "duty_and_responsibility": ["sec_001", "sec_003", "sec_005"],
    "self_discipline": ["sec_002", "sec_003", "sec_010"],
    "nature_and_cosmos": ["sec_002", "sec_007", "sec_009"],
    "relationships_with_others": ["sec_001", "sec_005", "sec_011"]
  },

  "routing_hints": {
    "good_for": [
      "dealing with things outside your control",
      "finding purpose in obligations",
      "acceptance of mortality",
      "emotional regulation",
      "leadership under pressure"
    ],
    "not_good_for": [
      "systematic logical argumentation",
      "epistemology",
      "political theory"
    ],
    "pairs_well_with": [
      "Letters from a Stoic - Seneca",
      "Discourses - Epictetus",
      "The Enchiridion - Epictetus"
    ]
  },

  "extraction_meta": {
    "model": "llama-3.1-8b-instruct",
    "date": "2026-02-05T...",
    "confidence": 0.92,
    "human_verified": false,
    "flags": [],
    "text_hash": "sha256:<hash of raw text>"
  }
}
```

### 2.4 System B: Reading Platform

```
┌──────────────────────────────────────────────────────────┐
│                    READING PLATFORM                       │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  DATA LAYER (Supabase/Postgres)                     │ │
│  │                                                      │ │
│  │  CANON (immutable)          USER (mutable)           │ │
│  │  ├── books                  ├── users                │ │
│  │  ├── book_artifacts         ├── saved_books          │ │
│  │  ├── sections               ├── highlights           │ │
│  │  ├── book_text (full)       ├── annotations          │ │
│  │  └── thematic_index         └── book_requests        │ │
│  └──────────────────────┬──────────────────────────────┘ │
│                         │                                 │
│  ┌──────────────────────▼──────────────────────────────┐ │
│  │  SERVICE LAYER                                       │ │
│  │                                                      │ │
│  │  canon_service      agent_service     user_service   │ │
│  │  - fetch sections   - intent classify - highlights   │ │
│  │  - fetch text       - route to books  - annotations  │ │
│  │  - thematic lookup  - section chat    - library      │ │
│  │  - immutable        - stateless       - mutable      │ │
│  └──────────────────────┬──────────────────────────────┘ │
│                         │                                 │
│  ┌──────────────────────▼──────────────────────────────┐ │
│  │  API LAYER (FastAPI, thin)                           │ │
│  │                                                      │ │
│  │  /ask          → agent_service.classify + route      │ │
│  │  /reader/{id}  → canon_service.get_section_text     │ │
│  │  /chat         → agent_service.section_companion    │ │
│  │  /library      → user_service.saved_books           │ │
│  │  /highlights   → user_service.highlights            │ │
│  │  /wishlist     → user_service.book_requests         │ │
│  │  /auth         → session management                  │ │
│  └──────────────────────┬──────────────────────────────┘ │
│                         │                                 │
│  ┌──────────────────────▼──────────────────────────────┐ │
│  │  FRONTEND (HTML templates, rendered server-side)     │ │
│  │                                                      │ │
│  │  Ask Screen → Routing Results → Reader               │ │
│  │                                                      │ │
│  │  Reader renders SECTION TEXT as HTML, not PDF.        │ │
│  │  Section nav from artifact structure.                 │ │
│  │  Highlights anchored to character offsets.            │ │
│  │  Chat scoped to current section only.                │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                           │
└──────────────────────────────────────────────────────────┘
```

### 2.5 How Routing Actually Works (with Taxonomy Artifacts)

```
User query: "I feel like nothing I do matters"

STEP 1: Intent Classification
  ┌───────────────────────────────────┐
  │ Input: "I feel like nothing       │
  │         I do matters"             │
  │                                   │
  │ Output:                           │
  │   domain: "philosophy"            │
  │   subdomain: "existentialism"     │
  │   secondary: "psychology"         │
  │   intent_type: "emotional_query"  │
  └─────────────┬─────────────────────┘
                │
STEP 2: Candidate Selection (no LLM, pure lookup)
  ┌─────────────▼─────────────────────┐
  │ Query thematic_index across all   │
  │ artifacts for matching themes:    │
  │   "meaninglessness"               │
  │   "purpose"                       │
  │   "absurdism"                     │
  │   "nihilism"                      │
  │   "existential_crisis"            │
  │                                   │
  │ Also check routing_hints.good_for │
  │ for fuzzy matches                 │
  │                                   │
  │ Result: 8-15 candidate sections   │
  │ across 4-6 books                  │
  └─────────────┬─────────────────────┘
                │
STEP 3: Reading Router (LLM, constrained)
  ┌─────────────▼─────────────────────┐
  │ Input:                            │
  │   - User question                 │
  │   - Candidate sections w/         │
  │     summaries + themes            │
  │                                   │
  │ Output: 2-4 "reading paths"       │
  │   each path = angle + 1-2 books   │
  │   at specific sections            │
  │                                   │
  │ Example:                          │
  │   Path 1: "Confronting the Absurd"│
  │     → Myth of Sisyphus, Ch 1-2    │
  │     → "Camus argues that..."      │
  │                                   │
  │   Path 2: "Finding Meaning Anyway"│
  │     → Man's Search for Meaning,   │
  │       Part I, Sections 3-5        │
  │     → "Frankl's logotherapy..."   │
  │                                   │
  │   Path 3: "The Stoic Response"    │
  │     → Meditations, Book 2         │
  │     → "Marcus reframes..."        │
  └───────────────────────────────────┘
```

---

## NOTEBOOK: SECTION 3 — USER FLOWS

### Flow 0: Entry

```
[ Landing Page ]
  │
  ├─── [ Continue as Guest ]
  │         │
  │         └──► [ Ask Screen ]
  │               (read-only: no highlights, no library, no chat)
  │
  └─── [ Sign In / Create Account ]
            │
            └──► [ Ask Screen ]
                  (full access: highlights, library, chat, requests)

RULES:
  - Guest sees the same routing results
  - Guest can read sections
  - Guest CANNOT: highlight, annotate, save, chat, request
  - Auth wall appears on first restricted action, not on entry
```

### Flow 1: Ask → Route → Read (the spine)

```
[ Ask Screen ]
  │
  │  "What are you trying to understand?"
  │  ┌─────────────────────────────────┐
  │  │ [                             ] │
  │  │         user types query        │
  │  └─────────────────────────────────┘
  │
  ├─── (submit) ───►
  │         │
  │         ▼
  │    [ Loading / Thinking ]
  │    "Searching the library..."
  │         │
  │         ▼
  │    ┌────────────────────────────────────────┐
  │    │ ROUTING RESULTS                        │
  │    │                                        │
  │    │ "Here's where to look:"                │
  │    │                                        │
  │    │ PATH 1: "Confronting the Absurd"       │
  │    │   📖 The Myth of Sisyphus — Camus      │
  │    │      Chapter 1: An Absurd Reasoning    │
  │    │      "Camus opens by asking whether    │
  │    │       life is worth living..."         │
  │    │   [ Open Section ]  [ Save Book ]      │
  │    │                                        │
  │    │ PATH 2: "Finding Meaning Anyway"       │
  │    │   📖 Man's Search for Meaning — Frankl │
  │    │      Part I: Experiences in a Camp     │
  │    │      "Frankl discovers that those      │
  │    │       who survived had purpose..."     │
  │    │   [ Open Section ]  [ Save Book ]      │
  │    │                                        │
  │    │ PATH 3: "The Stoic Response"           │
  │    │   📖 Meditations — Marcus Aurelius     │
  │    │      Book 2, Entries 1-5               │
  │    │      "Marcus writes that the universe  │
  │    │       is change, life is opinion..."   │
  │    │   [ Open Section ]  [ Save Book ]      │
  │    │                                        │
  │    │ ─────────────────────────────────────  │
  │    │ Missing a book?  [ Request It ]        │
  │    └────────────────────────────────────────┘
  │         │
  │         ├── [ Open Section ] ──► [ Reader ]
  │         ├── [ Save Book ]   ──► [ My Library ]
  │         └── [ Request It ]  ──► [ Wishlist ]
  │
  ├─── [ Browse Library ] ──► Flow 7
  ├─── [ My Library ]     ──► Flow 5
  └─── [ Wishlist ]        ──► Flow 6
```

### Flow 3: Reader (the core experience)

```
┌─────────────────────────────────────────────────────────────┐
│  READER VIEW                                                │
│                                                             │
│  ┌───────────────┐  ┌────────────────────────────────────┐  │
│  │ NAVIGATION    │  │ SECTION CONTENT                    │  │
│  │               │  │                                    │  │
│  │ ◁ Back to     │  │ BOOK 2                             │  │
│  │   results     │  │                                    │  │
│  │               │  │  Begin each day by telling         │  │
│  │ ▽ Introduction│  │  yourself: Today I shall be        │  │
│  │ ▶ Book 1      │  │  meeting with interference,        │  │
│  │ ▶ Book 2 ◄────│  │  ingratitude, insolence,           │  │
│  │   · Entry 1   │  │  disloyalty, ill-will, and         │  │
│  │   · Entry 2   │  │  selfishness — all of them         │  │
│  │   · Entry 3   │  │  due to the offenders' ignorance   │  │
│  │ ▶ Book 3      │  │  of what is good or evil.          │  │
│  │ ▶ Book 4      │  │                                    │  │
│  │ ...           │  │  ┌─ user highlight ──────────────┐ │  │
│  │ ▶ Book 12     │  │  │ But I have seen the beauty    │ │  │
│  │ ▽ Notes       │  │  │ of good, and the ugliness     │ │  │
│  │               │  │  │ of evil, and have recognized  │ │  │
│  │ ─────────────  │  │  │ that the wrongdoer has a     │ │  │
│  │ SECTION INFO  │  │  │ nature related to my own...   │ │  │
│  │               │  │  └──────────────────────────────┘ │  │
│  │ Themes:       │  │                                    │  │
│  │  · acceptance │  │  [user's annotation appears here]  │  │
│  │  · human      │  │                                    │  │
│  │    nature     │  │  ...text continues...              │  │
│  │  · equanimity │  │                                    │  │
│  │               │  │                                    │  │
│  │ ~8 min read   │  └────────────────────────────────────┘  │
│  │               │                                          │
│  │ Also explore: │  ┌────────────────────────────────────┐  │
│  │  · Book 6     │  │ SECTION CHAT                       │  │
│  │  · Seneca,    │  │                                    │  │
│  │    Letter 47  │  │ "What does Marcus mean by          │  │
│  │               │  │  'the wrongdoer has a nature       │  │
│  └───────────────┘  │   related to my own'?"             │  │
│                     │                                    │  │
│                     │ [scoped to this section only]      │  │
│                     │ [refuses out-of-scope questions]   │  │
│                     └────────────────────────────────────┘  │
│                                                             │
│  INTERACTIONS:                                              │
│  - Select text        → create highlight                    │
│  - Click highlight    → add/edit annotation                 │
│  - Click section nav  → jump to section (same book)         │
│  - Click "Also see"   → jump to different section/book      │
│  - Open chat          → section-scoped companion            │
│  - [ Save Book ]      → add to My Library                   │
│                                                             │
│  TEXT IS RENDERED HTML, NOT PDF.                             │
│  Character offsets from artifact anchor all interactions.    │
└─────────────────────────────────────────────────────────────┘
```

### Flow 4: Section Chat (Constrained)

```
[ Section Chat Panel ]
  │
  │  User asks: "What does Marcus mean by X?"
  │
  ├── (question is about THIS section's text)
  │     │
  │     ▼
  │   [ Answer rendered ]
  │   Context window = only this section's text
  │   LLM sees: section text + user's question
  │   LLM does NOT see: other books, other sections, internet
  │     │
  │     └──► [ Reader ] (chat stays open, user keeps reading)
  │
  ├── (question drifts outside this section)
  │     │
  │     ▼
  │   [ Scope Refusal ]
  │   "That question goes beyond this section.
  │    You might find what you're looking for in:"
  │     │
  │     └──► [ Suggested Section ] ──► [ Reader (new section) ]
  │
  └── (close chat)
        │
        └──► [ Reader ] (chat panel closes)

RULES:
  - No global chat. Ever.
  - No cross-book synthesis.
  - No "based on multiple sources."
  - Companion explains the TEXT, not the TOPIC.
  - If the user wants breadth, they go back to Ask.
```

### Flow 5: My Library

```
[ My Library ]
  │
  │  Grid of saved books with:
  │    - Cover/thumbnail
  │    - Title + Author
  │    - "X highlights"
  │    - Last read section
  │
  ├── [ Open Book ] ──► [ Reader ] (at last-read section)
  │
  ├── [ View Highlights ]
  │     │
  │     ▼
  │   [ Highlight List ]
  │   Grouped by book, then by section
  │   Each highlight shows:
  │     - Text snippet
  │     - Section title
  │     - Annotation (if any)
  │     - [ Jump to Context ] ──► [ Reader (anchored) ]
  │
  └── [ Remove Book ] ──► confirmation ──► removed
```

### Flow 6: Wishlist / Book Requests

```
[ Wishlist ]
  │
  ├── [ Request a Book ]
  │     │
  │     ▼
  │   [ Submit Form ]
  │     Title:  [          ]
  │     Author: [          ]
  │     Why:    [          ]
  │     [ Submit ]
  │         │
  │         └──► "Request submitted. We curate carefully."
  │
  ├── [ View My Requests ]
  │     Status: Pending / Under Review / Added / Declined
  │
  └── (book added notification)
        └──► [ Open Book ] ──► [ Reader ]
```

### Flow 7: Browse Library

```
[ Browse Library ]
  │
  │  ┌─────────────────────────────────────────┐
  │  │ Search: [                             ] │
  │  │                                         │
  │  │ Filter by:                              │
  │  │   Domain: [Philosophy ▼]                │
  │  │   Difficulty: [Any ▼]                   │
  │  │   Sort: [Title A-Z ▼]                   │
  │  └─────────────────────────────────────────┘
  │
  │  Book cards:
  │    ┌──────────────────────┐
  │    │ Meditations           │
  │    │ Marcus Aurelius       │
  │    │ Philosophy · Stoicism │
  │    │ 12 sections · ~2h     │
  │    │ [ Read ] [ Save ]     │
  │    └──────────────────────┘
  │
  ├── [ Read ]  ──► [ Reader ] (at section 1)
  └── [ Save ]  ──► [ My Library ]
```

---

## NOTEBOOK: SECTION 4 — FEATURES (V1 SCOPE, LOCKED)

### 4.1 Core Features

| Feature | Description | Depends On |
|---|---|---|
| **Ask** | Single input, natural language query | Intent Classifier agent |
| **Route** | 2-4 reading paths with rationale | Reading Router agent + taxonomy artifacts |
| **Read** | Rendered section text, not PDF | Canonical artifacts with section boundaries |
| **Navigate** | Chapter/section sidebar from artifact structure | Artifact `sections` array |
| **Highlight** | Select text → save with character offsets | Artifact offset system |
| **Annotate** | Private notes attached to highlights | User data layer |
| **Section Chat** | LLM explains THIS section only | Text Companion agent + section boundaries |
| **My Library** | Saved books, resume reading | User data layer |
| **Browse** | Filter/search all books | Book metadata from artifacts |
| **Wishlist** | Request missing books | Admin approval pipeline |

### 4.2 Features Explicitly NOT in V1

- Cross-book synthesis ("what do Camus AND Frankl say about meaning")
- Shared/public annotations
- Recommendations ("people who read X also read Y")
- Social features (following, sharing, discussion)
- Personalization algorithms
- Vector/semantic search across full corpus
- Reading streaks, gamification
- Feeds, trends, "popular highlights"

### 4.3 Admin Features (V1)

| Feature | Description |
|---|---|
| **Taxonomy Pipeline** | Run local LLM passes on new PDFs → artifacts |
| **Artifact Review** | Review flagged low-confidence artifacts |
| **Book Request Queue** | Approve/decline user requests |
| **Ingestion** | Import new PDFs → extract → taxonomy → publish |
| **Audit Log** | Track all admin actions |

---

## NOTEBOOK: SECTION 5 — MODALITY CONCERNS

This is the section you flagged as critical. "Throwing PDFs on screen" fails. Here's why and what replaces it.

### Why PDF Rendering Fails for This Product

```
PDF on screen:
  ✗ Cannot highlight and persist highlights
  ✗ Cannot anchor chat to a specific section
  ✗ Cannot navigate by chapter/section
  ✗ Cannot search within rendered text
  ✗ Cannot render responsively on mobile
  ✗ Cannot control typography for readability
  ✗ Cannot link between books/sections
  ✗ Cannot attach annotations at text positions
  ✗ Feels like "reading a scan" not "reading a book"

Rendered text from artifact:
  ✓ Full text selection and highlighting
  ✓ Character-offset-based highlight persistence
  ✓ Section-scoped chat (LLM context = section text)
  ✓ Chapter/section navigation sidebar
  ✓ Full-text search within book
  ✓ Responsive typography (font size, line height, width)
  ✓ Deep links: /reader/{book_id}/section/{section_id}
  ✓ Annotation anchoring
  ✓ Feels like "reading" not "viewing a file"
```

### What "Interactable" Means Concretely

```
INTERACTION 1: SELECT TEXT → HIGHLIGHT
  User drags across text
  Browser captures: start_offset, end_offset (relative to section)
  Converts to absolute offsets using artifact section boundaries
  Stores: {user_id, book_id, section_id, start_offset, end_offset, color}
  Renders: yellow background on that text span
  Survives: page reload, re-login, device switch

INTERACTION 2: CLICK HIGHLIGHT → ANNOTATE
  User clicks highlighted text
  Popover appears with:
    - The highlighted text
    - Text area for private note
    - [ Save ] [ Delete Highlight ]
  Annotation stored with highlight ID

INTERACTION 3: SECTION NAV → JUMP
  Sidebar shows artifact structure
  Click any section → scroll to that section
  URL updates: /reader/{book_id}#sec_003
  Section info panel updates (themes, reading time)

INTERACTION 4: CHAT ABOUT SECTION
  User opens chat panel
  System pre-loads current section text as context
  User asks question
  LLM responds using ONLY that section's text
  If out of scope → suggests other section
  Chat closes → back to reading

INTERACTION 5: CROSS-REFERENCE
  Sidebar shows "Also explore:" from artifact connects_to
  Click → navigates to that section (same or different book)
  Preserves context: "You came here from Meditations Book 2"
```

### Text Rendering Approach

```
HOW SECTION TEXT GETS TO THE BROWSER:

1. Backend receives request: GET /reader/{book_id}/section/{section_id}

2. Backend looks up artifact:
   - Finds section by ID
   - Gets start_offset, end_offset
   - Slices full text: book_text[start:end]

3. Backend processes text:
   - Split into paragraphs (double newline)
   - Wrap each paragraph in <p> with data-offset attribute
   - Each <p data-offset="2725"> preserves position
   - This is how highlights re-anchor on reload

4. Backend fetches user highlights for this section:
   - Returns list of {start_offset, end_offset, color, annotation}

5. Frontend renders:
   - Clean HTML paragraphs
   - JavaScript applies highlight overlays using offsets
   - Typography: serif font, ~65 chars per line, generous spacing
   - No PDF artifacts, no page numbers, no headers/footers
```

---

## NOTEBOOK: SECTION 6 — SEQUENCING (BUILD ORDER)

```
PHASE 0: TAXONOMY ENGINE (Week 1)
  ├── Day 1: Set up Ollama + model on your Mac
  ├── Day 2: Write single-book test (Meditations)
  ├── Day 3: Validate artifact against known structure
  ├── Day 4: Tune prompts on 10 diverse books
  ├── Day 5: Run batch on full corpus (overnight)
  ├── Day 6-7: Review flagged books, fix edge cases
  │
  │ GATE: 90%+ books have valid artifacts
  │ DELIVERABLE: artifacts/ directory with 500+ JSONs

PHASE 1: READER (Week 2-3)
  ├── New reader endpoint (serves section text, not PDF)
  ├── Section navigation sidebar
  ├── Text rendering with offset-preserving paragraphs
  ├── Highlight creation + persistence
  ├── Annotation CRUD
  │
  │ GATE: One book is fully readable and interactable
  │ DELIVERABLE: /reader/{id} works end to end

PHASE 2: ROUTING (Week 3-4)
  ├── Ingest artifacts into Supabase (thematic_index, routing_hints)
  ├── Intent classifier wired up
  ├── Reading router uses artifact data
  ├── Ask → Results → Reader flow works
  │
  │ GATE: User types question, gets section-level results, reads
  │ DELIVERABLE: Full Ask → Read flow

PHASE 3: CHAT + POLISH (Week 4-5)
  ├── Section-scoped chat companion
  ├── Cross-reference navigation
  ├── My Library + highlights view
  ├── Browse library with filters
  │
  │ GATE: 2-browser test (two users, full flow, no bugs)
  │ DELIVERABLE: V1 feature-complete
```

---

## NOTEBOOK: SECTION 7 — OPEN QUESTIONS (DECISIONS NEEDED)

```
1. LOCAL LLM MODEL CHOICE
   Options: Llama 3.1 8B, Qwen 2.5 7B, Mistral 7B
   Depends on: Your Mac specs (chip, RAM)
   Decision needed before: Phase 0 Day 1

2. DUPLICATE BOOKS
   You have: "1984 V1", "1984 V2", multiple versions
   Options: Pick best quality, merge, keep all
   Decision needed before: Phase 0 batch run

3. TEXT STORAGE
   Options: 
     a) Store full text in Supabase (current approach)
     b) Store full text in flat files, only metadata in Supabase
     c) Store text in artifact JSON, serve from filesystem
   Tradeoff: Supabase row size limits vs filesystem simplicity
   Decision needed before: Phase 1

4. FRONTEND FRAMEWORK
   Current: Server-rendered Jinja templates
   Options: Keep SSR, add HTMX for interactivity, SPA (React/Svelte)
   Reader highlighting requires JavaScript regardless
   Decision needed before: Phase 1

5. PDF AS FALLBACK?
   Keep "view original PDF" option alongside rendered text?
   Some books have diagrams, tables, mathematical notation
   Decision needed before: Phase 1

6. BOOK TYPES THAT RESIST STRUCTURE
   Poetry collections, aphorism books, dialogue-form texts
   Need special artifact types or handling
   Decision needed before: Phase 0 prompt tuning
```

---

That's the full notebook content. Six sections covering: current state (the honest truth), architecture (both systems), user flows (every screen transition), features (locked scope), modality (why text rendering not PDF), and sequencing (what order to build).

The taxonomy engine is the foundation. Everything else — routing, reading, highlighting, chat — depends on those artifacts being correct. That's where to start.


| | `LibraryofAlexandria-main` (both copies) | `Librarai/alexandria/` |
|---|---|---|
| **Framework** | Flask | **FastAPI** |
| **Focus** | Book *acquisition* (finding/downloading PDFs) | **Full reading platform** (ask, route, read) |
| **Agents** | None | **3 agents** (intent, router, companion) |
| **Reader** | PDF download link | **3 reader versions** (v1, v2, v3) |
| **Artifacts** | None | **Book artifact system** (sections, landmarks, paths) |
| **Taxonomy** | None | **v1 + v2 taxonomy** |
| **Highlighting** | None | **Implemented** (with chat tied to highlights) |
| **Extracted books** | 0 | **518 JSON files** |
| **Database** | SQLite only | **SQLite + Supabase** dual support |
| **User features** | None | **Saved books, highlights, annotations, wishlist** |
| **Templates** | Pipeline wizard + admin | **Reader, routing results, library, auth, admin** |
| **Python files** | ~24 (app) | **41 (app) + 13 (admin)** |

The `LibraryofAlexandria-main` repos are the **book acquisition pipeline** — how you find and download PDFs. That work is done. The `Librarai/alexandria/` repo is the **actual platform** — the reading experience, the agents, the routing. That's where all the value lives.

---

Now, I'm currently in **Ask mode** so I can't create the `manifest.md` file directly. I have two options for you:

1. **Switch me to Agent mode** and I'll create the file at `/Users/waleedraza/Downloads/Librarai/alexandria/manifest.md`
2. I can give you the full content right here and you paste it yourself

Either way, here's the complete `manifest.md` content. This is the spec document for whatever LLM session picks up this repo next:

---

```markdown
# MANIFEST — Alexandria Library Platform
## Authoritative Specification for Development

> This document is the single source of truth for any LLM or developer
> working in this repository. Read it entirely before touching any code.

---

## 0. WHAT THIS DOCUMENT IS

This is a combined:
- **Repo audit** (what exists, what's broken, what's missing)
- **Architecture spec** (how the system works)
- **User flow spec** (every screen, every transition)
- **Feature spec** (what's in V1, what's deferred)
- **Taxonomy engine spec** (how to parse books correctly)
- **Implementation sequence** (what to build in what order)

If something contradicts this document, this document wins.

---

## 1. PROJECT IDENTITY

**Name:** Alexandria / Library of Alexandria / Librarai
**Purpose:** A constrained, agent-guided reading system where users ask questions and are routed to specific sections of primary source texts.

**Core thesis:** Users bring confusion. The system routes them to books, chapters, passages. LLMs act only as guides, never as authorities. If a user walks away without reading, the system failed.

**What this is NOT:**
- ChatGPT with citations
- A PDF reader with AI
- A knowledge graph or recommendation engine
- A social reading platform
- A content feed or place for "answers"

---

## 2. CURRENT STATE AUDIT

### 2.1 Repository Location
```
/Users/waleedraza/Downloads/Librarai/alexandria/
```

This is the authoritative codebase. Two other repos exist in Downloads — both are copies
of an older Flask-based book acquisition pipeline. They are superseded by this repo.

### 2.2 Tech Stack
- **Backend:** FastAPI (Python)
- **Database:** SQLite (local) / Supabase (cloud), dual support
- **Agents:** 3 LLM agents (intent classifier, reading router, text companion)
- **Frontend:** Server-rendered Jinja2 templates
- **LLM Provider:** OpenAI (gpt-4o-mini), with mock mode for development

### 2.3 What Exists and Works

**Application Core:**
- `app/main.py` — FastAPI entry point, working
- `app/config.py` — Environment configuration, working
- `app/db/database.py` — Dual SQLite/Supabase support, working
- `app/db/schema.sql` — 9-table schema, complete

**Routes (7 files):**
- `app/routes/pages.py` — Public pages (index, library, book detail)
- `app/routes/auth.py` — Authentication routes
- `app/routes/reader.py` — Reader (PDF-based, needs replacement with text-based)
- `app/routes/library.py` — Library browsing
- `app/routes/wishlist.py` — Wishlist management
- `app/routes/ask.py` — Ask → Route → Read flow
- `app/routes/admin.py` — Admin dashboard (716 lines)

**Agents (10 files):**
- `app/agents/intent_classifier.py` — Query → domain/subdomain, real implementation
- `app/agents/reading_router.py` — Domain → book/chapter selection, real implementation
- `app/agents/text_companion.py` — Section-scoped explanations, real implementation
- `app/agents/book_agent.py` — Per-book intelligence (474 lines), real implementation
- `app/agents/domain_mapper.py` — Domain/subdomain mapping
- `app/agents/taxonomy.py` — Taxonomy v1
- `app/agents/taxonomy_v2.py` — Taxonomy v2
- `app/agents/contracts.py` — Agent I/O contracts
- `app/agents/llm_provider.py` — LLM client abstraction
- `app/agents/routing_cache.py` — Routing result cache

**Services (7 files):**
- `app/services/agent_service.py` — Orchestrates intent → router → companion
- `app/services/artifact_loader.py` — Loads artifact JSON from filesystem
- `app/services/canon_service.py` — Book/chapter access, read-only (432 lines)
- `app/services/chat_service.py` — Chat messages tied to highlights
- `app/services/text_renderer.py` — HTML text rendering with highlights
- `app/services/user_service.py` — Saved books,