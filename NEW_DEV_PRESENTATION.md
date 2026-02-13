# Alexandria Library — New Developer Presentation

> **Purpose:** Onboard a new developer. Articulate the origin story, the problem, the vision, and the path forward.

---

## 1. Origin Story: How This Started

**The DuckDuckGo API script.**

The project began with a simple script: using the DuckDuckGo API to search for and scrape books. The goal was to **acquire primary texts** — not summaries, not reviews, not SparkNotes — but the actual books themselves. Philosophy, classics, literature, whatever users might seek.

Why DuckDuckGo? Because Google Books has walls. PDFs of public domain and out-of-copyright works are scattered across the web. A script could find them, download them, and build a corpus.

That script evolved into a pipeline: **PDFs → extracted text → structured JSON**. Hundreds of books were processed. But extraction quality was terrible — regex chapter detection, single-blob fallbacks, garbage structure. So the next step was clear: **a taxonomy engine** — LLM-based structure detection, section boundaries, summaries, themes, routing hints. One canonical artifact per book.

Today, Alexandria is **not** the scraping pipeline. That's done. Alexandria is the **reading platform** — the thing that takes those artifacts and gets people to the right passage when they ask a question.

---

## 2. The AI Problem: What Online AI Doesn't Know

**Any AI you find online does not know the books.**

It knows what its **training data says about** the books. It knows summaries, reviews, secondary sources, Reddit threads, blog posts, CliffsNotes. It has never read Meditations. It has never read Metaphysics. It knows *about* them.

When you ask "What does Aristotle say about substance?" you get:
- A synthesis of what textbooks and summaries say
- Hallucinations dressed as quotes
- No way to verify — no citation to the actual text, no "go read Book 7, lines 1028a–1033b"

**That's our differentiator.** We route users to **the actual text**. The taxonomy artifacts contain the real content, section by section. When we send someone to a passage, they can read it, highlight it, chat about it — and the chat is **grounded in that passage**, not in "what GPT was trained on about Aristotle."

| What AI Knows              | What We Offer                        |
|----------------------------|--------------------------------------|
| Paraphrases of books       | The actual text                      |
| Hallucinated quotes        | Real passages with character offsets |
| "General knowledge"       | Section-specific summaries & themes |
| No verification possible   | Read it yourself, verify             |

---

## 3. Call to Action: Why This Matters

**No one reads anymore. It's not "brainrot enough."**

Books are long. Attention is short. Social feeds are infinite. Reading 300 pages to find one answer feels like a waste of time. So people ask ChatGPT. They get a paste. They move on. They never touch the source.

**Our call to action:** Enable people to **truly seek** — and **find** — the answers that seek them.

We don't replace reading. We **reduce the friction** to reading. You ask "What is wisdom?" → we route you to Metaphysics I.2, where Aristotle defines it. You read that section. You highlight. You chat about it. You take notes. The book does the work; we get you to the right place.

**The constraint is the product:** If a user can walk away without reading, we've failed.

---

## 4. Vision: Query → Relevant Sections, Across the Canon

```
┌──────────────────────────────────────────────────────────────────────────┐
│  USER QUERY                                                              │
│  "What does Plato get wrong about Forms?"                                │
│  "How do I deal with things outside my control?"                         │
│  "What is the relationship between virtue and happiness?"                 │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  LLM ROUTING (Intent + Reading Router)                                   │
│  - Classifies domain (philosophy, ethics, metaphysics, etc.)             │
│  - Uses thematic_index + routing_hints from taxonomy artifacts           │
│  - Returns 2–4 reading paths with specific sections                      │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  ROUTING RESULTS                                                         │
│  Path 1: Metaphysics, Book 7 — Aristotle's critique of Platonic Forms    │
│  Path 2: The Republic, Book 10 — Plato's own account                     │
│  Path 3: Categories — Aristotle's alternative theory                     │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  READER                                                                  │
│  - Renders section text (not PDF)                                        │
│  - Chapter navigation                                                   │
│  - Highlight → persists beyond refresh                                  │
│  - Chat with section (grounded, contextual)                             │
│  - Notes on highlights                                                  │
└──────────────────────────────────────────────────────────────────────────┘
```

**Target:** 10–12 books across genres (philosophy, ethics, fiction, self-help, classics). Every query routes to **relevant sections**, not "a book about the topic."

---

## 5. Core Features (What We Enable)

| Feature | Description |
|---------|-------------|
| **Ask** | Single input, natural language query |
| **Route** | LLM + taxonomy → 2–4 reading paths with rationale |
| **Read** | Rendered section text, chapter nav, no PDF required |
| **Highlight** | Select text → save → persists across refreshes (client-side DOM application) |
| **Chat** | Question about highlighted passage → Text Companion answers grounded in that text |
| **Notes** | Annotations attached to highlights |
| **My Library** | Saved books, resume reading (when auth is hooked up) |
| **Wishlist** | Request missing books (admin queue) |

**Critical:** Highlights and chat must work. Highlights must stay on the page. Chat must reference the actual passage and build on conversation history.

---

## 6. Current vs Desired State

### 6.1 Current Architecture (Simplified)

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ User Query  │────►│ Intent Classifier│────►│ Reading Router   │
│ (Ask page)  │     │ (mock or LLM)    │     │ (mock or LLM)   │
└─────────────┘     └──────────────────┘     └────────┬────────┘
                                                      │
                     ┌────────────────────────────────┼────────────────────────────────┐
                     │                                │                                │
                     ▼                                ▼                                ▼
              ┌──────────────┐                 ┌──────────────┐                 ┌──────────────┐
              │ Artifact     │                 │ taxonomy     │                 │ Canon        │
              │ Loader       │                 │ (thematic_   │                 │ Service      │
              │ (JSON files) │                 │  index,      │                 │ (sections,   │
              │              │                 │  routing_     │                 │  text)       │
              │              │                 │  hints)      │                 │              │
              └──────────────┘                 └──────────────┘                 └──────────────┘
                     │                                │                                │
                     └────────────────────────────────┼────────────────────────────────┘
                                                      │
                                                      ▼
                                              ┌─────────────────┐
                                              │ Reader          │
                                              │ (text, highlights│
                                              │  chat, notes)   │
                                              └────────┬────────┘
                                                       │
                                                       ▼
                                              ┌─────────────────┐
                                              │ SQLite          │
                                              │ (highlights,    │
                                              │  annotations,   │
                                              │  chat_messages) │
                                              └─────────────────┘
```

**Current:** 1 book (Metaphysics) in taxonomy-pipeline artifacts. SQLite for user data. Mock or real LLM agents. Auth is stub (anonymous).

### 6.2 Desired State (Path to Production)

```
┌──────────────────────────────────────────────────────────────────────────┐
│  INGESTION LAYER (Offline / Admin)                                        │
│  PDF → taxonomy-pipeline → artifact JSON → (optional) Supabase/Postgres   │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  PLATFORM (Online)                                                        │
│  - 10–12 books in artifact store                                         │
│  - Ask → Route → Read (full flow)                                        │
│  - Highlights persist (SQLite or cloud DB)                               │
│  - Auth (Supabase Auth or similar)                                       │
│  - Proper DB when scale demands (Postgres/Supabase)                      │
│  - Deploy: Render, Fly.io, or Vercel + serverless                        │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 7. Path to Deployment (First Steps)

| Step | Description |
|------|-------------|
| **1. Ingest every PDF into taxonomy** | Run taxonomy-pipeline on all target books. Output: `artifacts/{book_id}.json`. |
| **2. Test routing as we go** | Add books incrementally. Verify "What is X?" routes to correct sections. |
| **3. Enhance LLM to ask questions** | Intent classifier and router prompts can be improved. Text Companion can ask clarifying questions. |
| **4. Highlights persist** | ✅ Done (client-side DOM + SQLite). Ensure works across sessions when auth is added. |
| **5. Hook up proper DB when needed** | SQLite fine for POC. Migrate to Postgres/Supabase when: multi-user, scale, or persistence beyond single host. |
| **6. Auth** | Replace stub auth with real auth (Supabase Auth, or similar). Tie highlights/notes to user_id. |

---

## 8. Codebase Guide

### 8.1 Project Layout

```
alexandria/
├── app/                    # FastAPI application
│   ├── main.py             # Entry point, routes, startup
│   ├── config.py           # Settings (USE_MOCK_AGENTS, OPENAI_API_KEY, etc.)
│   ├── agents/             # LLM agents (stateless, pure)
│   │   ├── intent_classifier.py   # Query → domain
│   │   ├── reading_router.py     # Domain + taxonomy → section recommendations
│   │   ├── text_companion.py     # Passage + question → explanation
│   │   ├── contracts.py         # I/O dataclasses
│   │   ├── llm_provider.py      # OpenAI client abstraction
│   │   └── ...
│   ├── services/           # Business logic
│   │   ├── agent_service.py     # Orchestrates intent → router → companion
│   │   ├── artifact_loader.py   # Reads artifact JSON from filesystem
│   │   ├── canon_service.py     # Book/chapter/text access (artifact-first)
│   │   ├── user_service.py     # Highlights, annotations (SQLite)
│   │   └── chat_service.py     # Chat messages per highlight
│   ├── routes/             # HTTP handlers (thin)
│   │   ├── pages.py        # /, /library, etc.
│   │   ├── ask.py          # POST /ask — routing
│   │   ├── reader.py       # /read/{book_id} — reader, highlights, chat
│   │   ├── auth.py         # Login/register (currently stub)
│   │   └── ...
│   ├── db/
│   │   ├── database.py     # SQLite connection
│   │   ├── schema.sql     # Tables: users, highlights, annotations, chat_messages
│   │   └── ...
│   └── domain/             # Entity models (book, chapter, highlight, user)
│
├── taxonomy-pipeline/      # Separate project: PDF → artifact JSON
│   ├── src/
│   │   ├── pipeline1/     # s1_extraction → s7_validation
│   │   ├── cli.py
│   │   └── ...
│   └── data/artifacts/    # Output: metaphysics_aristotle.json, etc.
│
├── templates/              # Jinja2
│   ├── base.html
│   ├── index.html         # Ask page
│   ├── routing_results.html
│   ├── reader.html        # Reader with highlights sidebar
│   └── ...
│
├── static/
│   ├── css/
│   └── js/reader.js       # Highlight application (client-side), chat panel
│
├── admin/                  # CLI scripts (ingest, extract, etc.)
├── data/                   # SQLite DB, logs (gitignored)
└── docs/                   # Architecture, onboarding (this file's home)
```

### 8.2 Request Flow: Ask → Route → Read

```
1. User submits question on / (index.html form posts to /ask)
2. ask.py calls AgentService.route_question(question)
3. AgentService:
   - IntentClassifier.classify(question) → domain
   - ReadingRouter.route(question, available_books, chapters_by_book) → recommendations
4. routing_results.html renders paths; each has link to /read/{book_id}?chapter={section_number}
5. reader.py loads artifact section text, highlights for user, renders reader.html
6. reader.js applies highlights client-side, handles create/delete, chat
```

### 8.3 Data Flow: Artifacts vs DB

| Data | Source | Purpose |
|------|--------|---------|
| Book metadata, sections, text | `taxonomy-pipeline/data/artifacts/*.json` | Canon. Single source of truth. |
| Highlights, annotations, chat | SQLite (`data/alexandria.db`) | User-specific, mutable. |

**Artifact schema** (per book): `sections[]` with `id`, `title`, `start_offset`, `end_offset`, `summary`, `key_themes`; `synthesis.thematic_index`, `synthesis.routing_hints`.

### 8.4 Key Files to Know

| File | Purpose |
|------|---------|
| `app/main.py` | App bootstrap, route registration |
| `app/services/artifact_loader.py` | `get_available_books()`, `get_sections_as_chapters()`, `build_theme_to_sections()` |
| `app/services/canon_service.py` | Wraps artifact_loader; `get_book()`, `get_chapters()`, `get_chapter_text()` |
| `app/agents/reading_router.py` | Uses taxonomy to score/select sections for user query |
| `app/routes/reader.py` | Reader view, highlight CRUD, chat |
| `static/js/reader.js` | Client-side highlight application, chat panel |
| `taxonomy-pipeline/README.md` | How to run pipeline |
| `manifest.md` | Full architecture, user flows, sequencing |

### 8.5 Run Locally

```bash
# Install
pip install -r requirements.txt

# Run
uvicorn app.main:app --reload --port 5000

# Open
open http://localhost:5000
```

---

## 9. Summary for the New Dev

1. **Origin:** DuckDuckGo API script → PDF scraping → taxonomy pipeline → reading platform.
2. **Problem:** AI doesn't know books; it knows what data says about them. We route to real text.
3. **Mission:** Get people to the passages that answer their questions. Highlight, chat, take notes.
4. **Tech:** FastAPI, artifact JSON (filesystem), SQLite (user data), Jinja2 + vanilla JS.
5. **Next steps:** Ingest more books, refine routing, add auth, deploy when ready.

---

*The constraint is the product. If a user can walk away without reading, we've failed.*
