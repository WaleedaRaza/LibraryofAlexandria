# Alexandria Library

> **Wikipedia's lost opportunity for books.**

A constrained, agent-guided reading system that grows with every user request.

---

## 🚀 NEW DEVELOPER? → [`START_HERE.md`](./START_HERE.md) ← START HERE

**Full onboarding path:**
1. [`START_HERE.md`](./START_HERE.md) (1 min) - Welcome
2. [`QUICK_START.md`](./QUICK_START.md) (5 min) - Overview & local setup
3. [`ONBOARDING.md`](./ONBOARDING.md) (20 min) - Full context & roadmap
4. [`PHASE2_CHECKLIST.md`](./PHASE2_CHECKLIST.md) - Your daily checklist
5. [`ROADMAP_VISUAL.md`](./ROADMAP_VISUAL.md) - Visual roadmap
6. [`ARCHITECTURE.md`](./ARCHITECTURE.md) - System design deep dive

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
- A recommendation engine
- A place for "answers"

**We route to books. We don't replace them.**

## What this is NOT

- ChatGPT with citations
- A PDF reader with AI
- A knowledge graph
- A recommendation engine
- A social reading app
- A place for "answers"

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

## Deploy to Vercel

```bash
# Install Vercel CLI
npm i -g vercel

# Deploy
vercel
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

