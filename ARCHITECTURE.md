# Architecture — Alexandria Library

> Canonical architecture reference. Every layer, every connection, every data flow.

---

## 1. System Overview

Alexandria has two systems. They share zero code. The only interface between them is the **artifact JSON**.

```
SYSTEM A: TAXONOMY PIPELINE              SYSTEM B: READING PLATFORM
(offline, local Mac, Ollama)              (online, user-facing, FastAPI)

┌─────────────────────────────┐          ┌─────────────────────────────┐
│  PDF → 7-stage pipeline     │          │  Ask → Route → Read         │
│  → artifact JSON per book   │──JSON──► │  Highlights, Chat, Notes    │
└─────────────────────────────┘          └─────────────────────────────┘
```

---

## 2. System A: Taxonomy Pipeline

**Location:** `taxonomy-pipeline/`

**Purpose:** Transform raw PDFs into structured, navigable, semantically-tagged artifacts. Run once per book. Output is immutable.

### Pipeline Stages

```
PDF
 │
 ▼
┌──────────────────────────────────────────────────────────────────┐
│  S1: Extraction (PyMuPDF, no LLM)                                │
│  Raw text, page boundaries, TOC if present, OCR detection        │
├──────────────────────────────────────────────────────────────────┤
│  S2: Cleaning (deterministic, no LLM)                            │
│  Strip headers/footers, rejoin hyphenation, normalize whitespace │
│  Output: clean_text + content_hash (SHA-256, immutable)          │
├──────────────────────────────────────────────────────────────────┤
│  S3: Structure (1 LLM call)                                      │
│  Classify: book_type, hierarchy, front/back matter               │
├──────────────────────────────────────────────────────────────────┤
│  S4: Boundaries (N LLM calls, sliding window)                    │
│  Find section breaks → list of sections with char offsets        │
├──────────────────────────────────────────────────────────────────┤
│  S5: Enrichment (1 LLM call per section)                         │
│  Per section: summary, key_themes, notable_passages, difficulty  │
├──────────────────────────────────────────────────────────────────┤
│  S6: Synthesis (1 LLM call per book)                             │
│  Book-level: domain, thematic_index, routing_hints, cross-refs   │
├──────────────────────────────────────────────────────────────────┤
│  S7: Validation (no LLM)                                         │
│  Offset coverage, no overlaps, enrichment complete, confidence   │
└──────────────────────────────────────────────────────────────────┘
 │
 ▼
ARTIFACT JSON (one per book, stored in data/artifacts/)
```

### CLI

```bash
python -m src.cli process --pdf data/pdfs/book.pdf        # Single book
python -m src.cli batch --pdf-dir data/pdfs/               # All books
python -m src.cli inspect --artifact data/artifacts/x.json # Inspect
python -m src.cli check-llm                                # Verify Ollama
```

### Checkpoint System

Each stage checkpoints to `data/checkpoints/{book_id}/s{N}_{name}.json`. Resume from failure. Re-run from specific stage with `--rerun-from`.

---

## 3. The Canonical Artifact (Data Contract)

This is the single most important data structure. Everything downstream depends on it.

```json
{
  "artifact_version": "1.0.0",
  "book_id": "metaphysics_aristotle",
  "generated_at": "2026-02-08T...",

  "source": {
    "filename": "Metaphysics-Aristotle.pdf",
    "page_count": 142,
    "is_ocr": false,
    "extraction_quality": 0.92
  },

  "text": {
    "content": "THE FULL CLEAN TEXT...",
    "char_count": 187432,
    "word_count": 38210,
    "content_hash": "sha256:..."
  },

  "structure": {
    "book_type": "treatise",
    "structure_pattern": "books > chapters",
    "hierarchy_levels": 2
  },

  "sections": [
    {
      "id": "sec_001",
      "title": "Chapter 1",
      "start_offset": 2725,
      "end_offset": 12400,
      "summary": "...",
      "key_themes": ["wisdom", "knowledge", "experience"],
      "difficulty": "moderate"
    }
  ],

  "synthesis": {
    "domain": "philosophy",
    "subdomains": ["metaphysics", "ontology"],
    "thematic_index": {
      "substance": ["sec_007", "sec_008", "sec_009"],
      "form": ["sec_007", "sec_010"]
    },
    "routing_hints": {
      "good_for": ["understanding being qua being", "..."],
      "not_good_for": ["practical ethics", "..."]
    }
  },

  "quality": {
    "confidence": 0.87,
    "flags": []
  }
}
```

### Schema Rules

1. **`text.content` is immutable.** All offsets reference this string. If you re-clean, all downstream data invalidates.
2. **Section offsets are contiguous.** `sections[n].end_offset == sections[n+1].start_offset`. No gaps, no overlaps.
3. **Section IDs are stable.** `fm_001`, `sec_001`, `bm_001`. Referenced by thematic_index, highlights, annotations.
4. **Notable passage offsets are absolute** — they reference `text.content`, not relative to their section.

---

## 4. System B: Reading Platform

**Location:** `app/`

**Purpose:** Route users to relevant sections, render text, enable interaction.

### Layer Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│  ROUTES (thin HTTP handlers)                                     │
│  pages.py  ask.py  reader.py  library.py  wishlist.py  auth.py  │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│  SERVICES (business logic)                                       │
│  agent_service    canon_service    user_service    chat_service   │
│  artifact_loader  request_service                                │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│  AGENTS (stateless, pure LLM wrappers)                           │
│  intent_classifier    reading_router    text_companion           │
│  contracts.py         llm_provider.py                            │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│  DATA                                                            │
│  Artifacts (JSON files)  ←  Canon: immutable, read-only          │
│  SQLite / Postgres       ←  User data: mutable                   │
└─────────────────────────────────────────────────────────────────┘
```

### Request Flows

#### Ask → Route → Read

```
POST /ask
  │  question="What is wisdom?"
  ▼
ask.py → AgentService.route_question(question)
  │
  ├── IntentClassifier.classify(question)
  │   → IntentResult(domain="philosophy", subdomain="epistemology")
  │
  ├── ReadingRouter.route(question, books, chapters_by_book)
  │   │  Uses artifact thematic_index + key_themes + summaries
  │   │  Scores sections by keyword overlap with themes
  │   │  Returns top matches as reading paths
  │   → RoutingResult(paths=[ReadingPath(...), ...])
  │
  ▼
routing_results.html
  │  Shows 2–4 reading paths with rationale
  │  Each path links to /read/{book_id}?chapter={N}&context={rationale}
  ▼
GET /read/metaphysics_aristotle?chapter=2
  │
  ├── canon_service.get_chapter_text(book_id, section_id)
  │   → Section text sliced from artifact text.content[start:end]
  │
  ├── user_service.get_highlights(user_id, section_id)
  │   → List of highlights from SQLite
  │
  ▼
reader.html + reader.js
  │  Text rendered as <p> tags
  │  JS applies highlights client-side (DOM text search)
  │  Sidebar: highlights list, note/chat/delete actions
```

#### Highlight → Chat

```
User selects text in reader
  │
  ▼
POST /read/{book_id}/highlight
  │  chapter_id, selected_text, color
  │  → Returns { highlight_id }
  │  → JS applies highlight to DOM instantly (no reload)
  ▼
User clicks "Chat" on highlight
  │
  ▼
POST /read/{book_id}/highlight/{hl_id}/chat
  │  question="What does this mean?"
  │
  ├── chat_service.add_message(hl_id, "user", question)
  ├── chat_service.get_messages(hl_id) → conversation history
  │
  ├── TextCompanion.explain(
  │     book_title, chapter_title, selected_text,
  │     question, routing_context=history
  │   )
  │   │  Mock: keyword-based responses grounded in passage
  │   │  LLM: OpenAI with passage as context
  │   → CompanionResponse(explanation="...")
  │
  ├── chat_service.add_message(hl_id, "assistant", explanation)
  │
  ▼
partials/chat_response.html → JS renders in chat panel
```

---

## 5. Data Architecture

### Canon (Immutable)

| Source | Location | What |
|--------|----------|------|
| Artifact JSONs | `taxonomy-pipeline/data/artifacts/` | Full text, sections, themes, routing hints |
| Loaded by | `artifact_loader.py` | Functions: `get_available_books()`, `load_artifact()`, `get_book_text()`, `get_sections_as_chapters()`, `build_theme_to_sections()`, `get_routable_sections()` |
| Wrapped by | `canon_service.py` | `get_book()`, `get_chapters()`, `get_chapter_text()`, `get_chapter_by_number()` |

### User Data (Mutable)

| Table | Columns | Purpose |
|-------|---------|---------|
| `users` | id, email, password_hash, display_name, role | Auth (currently stub) |
| `highlights` | id, user_id, book_id, section_id, selected_text, color | Text selections |
| `annotations` | id, highlight_id, text | Notes on highlights |
| `chat_messages` | id, highlight_id, role, content | Chat threads per highlight |
| `schema_versions` | version, description | Migration tracking |
| `book_requests` | **MISSING** — needs to be added | Wishlist / book request queue |

### Schema Location

- SQLite: `app/db/schema.sql` (version 10, artifact-first)
- Postgres: `app/db/schema_postgres.sql` (needs update to match)

---

## 6. Agent Architecture

Three agents. All stateless. All replaceable. All follow contracts.

```
┌─────────────────────────────────────────────────────────────┐
│  AGENT               INPUT                   OUTPUT          │
├─────────────────────────────────────────────────────────────┤
│  IntentClassifier    question (str)          IntentResult     │
│                                              - domain         │
│                                              - subdomain      │
│                                              - confidence     │
├─────────────────────────────────────────────────────────────┤
│  ReadingRouter       question, books,        RoutingResult    │
│                      chapters_by_book        - paths[]        │
│                                              - each: book,    │
│                                                sections,      │
│                                                rationale      │
├─────────────────────────────────────────────────────────────┤
│  TextCompanion       book_title, chapter,    CompanionResponse│
│                      selected_text,          - explanation    │
│                      question,               - is_valid       │
│                      routing_context         - refusal_reason │
└─────────────────────────────────────────────────────────────┘
```

**Contracts:** Defined in `app/agents/contracts.py` as dataclasses.

**Modes:** Each agent has `_mock_*` (deterministic, no API) and `_llm_*` (real OpenAI). Controlled by `USE_MOCK_AGENTS` env var.

**Orchestration:** `AgentService` in `app/services/agent_service.py` chains them: classify → route → (optionally) companion.

---

## 7. Frontend Architecture

Server-rendered Jinja2 templates + vanilla JavaScript.

| Template | Purpose |
|----------|---------|
| `base.html` | Layout, nav, CSS/JS includes |
| `index.html` | Ask page (question input) |
| `routing_results.html` | Reading paths from routing |
| `reader.html` | Text reader with highlight sidebar, chat panel |
| `library.html` | Browse all books |
| `wishlist.html` | Book request form |
| `partials/chat_response.html` | Chat response fragment |

### JavaScript (`static/js/reader.js`)

- **Highlight application:** On page load, walks DOM text nodes, normalizes whitespace, wraps matching text in `<span class="hl hl--{color}">`.
- **Instant creation:** After POST succeeds, applies highlight to DOM without reload.
- **Delete:** Unwraps span, removes sidebar card.
- **Chat panel:** Slide-in panel, loads history, sends messages, renders responses.

### CSS (`static/css/`)

- `main.css` — Global styles, nav, library, wishlist
- `reader.css` — Reader layout, sidebar, annotations

---

## 8. Directory Map

```
alexandria/
├── app/                         # FastAPI application
│   ├── main.py                  # Entry point, route registration, startup
│   ├── config.py                # Settings from env vars
│   ├── __init__.py              # Template setup
│   │
│   ├── agents/                  # LLM agents (stateless)
│   │   ├── contracts.py         # I/O dataclasses
│   │   ├── intent_classifier.py # Query → domain
│   │   ├── reading_router.py    # Domain → sections (uses taxonomy)
│   │   ├── text_companion.py    # Passage → explanation
│   │   ├── llm_provider.py      # OpenAI client
│   │   ├── domain_mapper.py     # Domain/subdomain mapping
│   │   ├── taxonomy.py          # Taxonomy v1
│   │   ├── taxonomy_v2.py       # Taxonomy v2 (artifact-based)
│   │   ├── routing_cache.py     # Cache for routing results
│   │   └── book_agent.py        # Per-book intelligence
│   │
│   ├── services/                # Business logic
│   │   ├── agent_service.py     # Orchestrates agents
│   │   ├── artifact_loader.py   # Reads artifact JSON from filesystem
│   │   ├── canon_service.py     # Book/chapter/text access
│   │   ├── user_service.py      # Highlights, annotations (SQLite)
│   │   ├── chat_service.py      # Chat messages per highlight
│   │   ├── request_service.py   # Book requests (needs schema fix)
│   │   └── text_renderer.py     # HTML rendering helpers
│   │
│   ├── routes/                  # HTTP handlers
│   │   ├── pages.py             # /, /about
│   │   ├── ask.py               # POST /ask
│   │   ├── reader.py            # /read/{book_id}
│   │   ├── library.py           # /library
│   │   ├── wishlist.py          # /wishlist (needs auth + schema)
│   │   ├── auth.py              # Login/register (stub)
│   │   └── admin.py             # Admin dashboard
│   │
│   ├── db/                      # Database
│   │   ├── database.py          # SQLite connection
│   │   ├── schema.sql           # Current schema (v10)
│   │   ├── schema_postgres.sql  # Postgres variant
│   │   └── migrations/          # Incremental migrations
│   │
│   ├── domain/                  # Entity models
│   │   ├── book.py, chapter.py, highlight.py, user.py
│   │   └── book_artifacts.py
│   │
│   └── middleware/
│       └── rate_limit.py
│
├── taxonomy-pipeline/           # PDF → artifact (separate project)
│   ├── src/
│   │   ├── cli.py               # CLI entry point
│   │   ├── config.py, llm.py, schema.py
│   │   └── pipeline1/           # 7-stage pipeline
│   │       ├── runner.py        # Orchestrator
│   │       └── s1–s7_*.py       # Stages
│   ├── data/
│   │   ├── artifacts/           # Output JSONs
│   │   ├── checkpoints/         # Resume points
│   │   ├── pdfs/                # Input PDFs
│   │   └── flagged/             # Low-confidence
│   └── config.yaml
│
├── templates/                   # Jinja2 templates
├── static/                      # CSS, JS
├── admin/                       # CLI scripts for ingestion/maintenance
├── mockups/                     # HTML mockups for all screens
├── tests/                       # Test files
├── docs/                        # Documentation index
│
├── NEW_DEV_PRESENTATION.md      # Onboarding for new devs
├── CURRENT_VS_DESIRED_STATE.md  # Where we are vs where we're going
├── ARCHITECTURE.md              # This file
├── DEPLOYMENT_ISSUES.md         # GitHub issues spec
├── manifest.md                  # Deep reference (flows, features, sequencing)
├── taxonomy.md                  # Taxonomy pipeline spec
├── render.yaml                  # Render.com deploy config
└── requirements.txt             # Python dependencies
```

---

## 9. Configuration

| Env Var | Purpose | Default |
|---------|---------|---------|
| `DEBUG` | Debug mode | `true` |
| `SECRET_KEY` | Session signing | (required) |
| `USE_MOCK_AGENTS` | Mock LLM agents | `true` |
| `OPENAI_API_KEY` | OpenAI API key | (none — forces mock) |
| `DATABASE_URL` | Postgres connection | (none — uses SQLite) |
| `SUPABASE_URL` | Supabase project URL | (none) |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase key | (none) |

---

*This is the canonical architecture document. Keep it updated as the system evolves.*
