# LibXNDR

The reader-facing library, founded with Waleed's Library. The local codebase retains some Alexandria names while the product identity moves to LibXNDR.

> Product direction and release gates: [LibXNDR product plan](docs/LIBXNDR_PRODUCT_PLAN.md).

> Current built/live status and external blockers: [LibXNDR launch board](docs/LAUNCH_BOARD.md).

> Reader-facing deployment for the 552-book collection: [DEPLOY_WALEEDS_LIBRARY.md](DEPLOY_WALEEDS_LIBRARY.md)

> **Wikipedia's lost opportunity for books.**

A constrained, agent-guided reading system. Users ask questions → routed to relevant book sections → read, highlight, chat, take notes.

---

## New Developer? Start Here

1. **[NEW_DEV_PRESENTATION.md](./NEW_DEV_PRESENTATION.md)** — Origin story, vision, codebase guide, path to deployment. **Read first.**
2. **[docs/README.md](./docs/README.md)** — Documentation index.
3. **[manifest.md](./manifest.md)** — Full architecture, user flows, sequencing (deep reference).

---

## What This Is

- Users ask questions → Routed to **specific book passages**
- Users request books → We curate and add **for everyone**
- Every request grows the library → **Network effects**

**Constraint**: If a user can walk away without reading, the system has failed.

---

## What This Is NOT

- ChatGPT with citations
- A PDF reader with AI
- A private Reading Companion that searches a reader's saved passages and cites the exact highlights it used
- A recommendation engine
- A place for "answers"

**We route to books. We don't replace them.**

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the server
uvicorn app.main:app --reload --port 5000

# Open in browser
open http://localhost:5000
```

## Ingest Books

```bash
# Ingest a single PDF
python -m admin.ingest_books --pdf /path/to/book.pdf --title "Book Title" --author "Author"

# Ingest a directory of PDFs
python -m admin.ingest_books --dir /path/to/pdfs/
```

## Local PDF discovery desk

The private dashboard at `http://127.0.0.1:5000/desk` accepts one title per line
(`Title — Author` is supported), or loads the [Launch 72](library/reading_lists/launch_72.json)
in six batches of twelve. It searches, deduplicates, verifies PDF responses,
checks the first pages and book length where feasible, and ranks candidates with
an inspectable evidence trail. Every verified PDF can be opened manually, regardless
of host. It never auto-opens tabs and is disabled when `ENV=production`.

The desk keeps the original link and lets Waleed select candidates for a shortlist,
copy them, or export Chrome bookmarks. A verified PDF does not establish permission
to publish it in the public reader. Login walls, previews, dead links, HTML
masquerading as PDFs, and suspected guides remain visible for review.

The current sourcing pass is saved in `data/launch_72_sourcing.json` and can be
loaded with **Load sourced run**. The generated [first-look list](library/reading_lists/launch_72_first_looks.md)
and [Chrome bookmark import](library/reading_lists/launch_72_first_looks_bookmarks.html)
contain the candidates that passed the book-length checks. To reproduce a pass:

```bash
.venv/bin/python -m admin.source_launch_list --all
.venv/bin/python -m admin.source_launch_list --retry-missing
.venv/bin/python -m admin.source_launch_list --reassess
.venv/bin/python -m admin.apply_manual_sources
.venv/bin/python -m admin.build_launch_report
.venv/bin/python -m admin.stage_launch_links
```

The last command stages the 51 first-look links in ignored `data/link_books_staged.json`.
Browse their book jackets and source-link detail pages at
`http://127.0.0.1:5000/library?preview_links=1&kind=links`. These local draft
records do **not** enter the public catalog; they are not hosted PDFs and do not
offer in-app highlights. Each detail retains the direct PDF link, the original
indexed link, and a bookmark-bar action. Their jackets are generated placeholders
until a reviewed local file supplies an actual cover.

After reviewing an individual source for public sharing, promote only that title:

```bash
.venv/bin/python -m admin.approve_link_books --title "Dracula" --confirm-public-sharing
```

This writes an explicitly approved record to `library/link_catalog.json` for a
later deployment. Do not treat PDF reachability or page count as a rights decision.

Signed-in readers use `/library/find` rather than the local desk. That product flow accepts up to 50 titles, saves progress and ranked candidates in the database, resumes after a reload or app restart, and lets readers save selected links privately for review. The browser advances the run one title at a time so no request exceeds Firebase Hosting's 60-second dynamic timeout.

## Project Structure

```
alexandria/
├── app/
│   ├── routes/      # HTTP handlers (thin, declarative)
│   ├── services/    # Business logic
│   ├── agents/      # LLM wrappers (pure, stateless)
│   ├── domain/      # Entity logic
│   └── db/          # Database layer
├── templates/       # Jinja2 templates
├── static/          # CSS, JS
├── admin/           # CLI tools
└── CURSOR_CONTEXT.md # Sacred document
```

## The Three Agents

1. **Intent Classifier**: Query → domain mapping
2. **Reading Router**: Domain → chapter recommendations  
3. **Text Companion**: Selected text → clarification

All agents are stateless, deterministic, replaceable.

## Core Constraints

1. **Canon is sacred** — `book_text.content` is the single source of truth
2. **Reading is primary** — No summaries, no global chat
3. **LLMs are tools** — Constrained by contracts, not creative

## Deploy

The planned public route is Firebase Hosting in front of a Cloud Run FastAPI container, with Supabase for accounts, reading data, and private PDFs. A domain bought on Vercel can be pointed to Firebase via DNS. See [DEPLOY_WALEEDS_LIBRARY.md](DEPLOY_WALEEDS_LIBRARY.md) for prerequisites and checks. The older `render.yaml` is not the chosen deployment path.

The dedicated Firebase project is `libxndr`. See [deploy/README.md](deploy/README.md) for the exact staging build, secret, reviewer, collection-upload, and domain procedure. Run the local collection preflight before any release:

```bash
.venv/bin/python -m admin.launch_preflight \
  --pdf-root '/Volumes/Extreme SSD/Downloads/Librarai/alexandria/batch1books'
```

## Environment Variables

```
DEBUG=true
SECRET_KEY=your-secret-key
USE_MOCK_AGENTS=true
OPENAI_API_KEY=sk-...
```

---

*The constraint is the product.*
