# Current vs Desired State — Alexandria Library

> Canonical reference. If reality differs from this document, update this document.

---

## 1. Current State (February 2026)

### What Works

| Component | Status | Details |
|-----------|--------|---------|
| **FastAPI app** | Running | `uvicorn app.main:app --reload` on port 5000/5001 |
| **Ask → Route → Read** | Working | User asks question → intent classifier → reading router → reader view |
| **Taxonomy artifact** | 1 book | `metaphysics_aristotle.json` — 157 sections, summaries, themes, routing hints |
| **Text reader** | Working | Renders section text as HTML paragraphs, chapter nav sidebar |
| **Highlights** | Working | Client-side DOM application, persists in SQLite, survives refresh |
| **Chat** | Working | Grounded in selected passage, varies by question type, tracks conversation history |
| **Annotations** | Working | Notes on highlights, CRUD via sidebar |
| **Routing intelligence** | Working | Mock router uses taxonomy themes/summaries for section scoring; LLM route enriched with section data |
| **Taxonomy pipeline** | Working | 7-stage pipeline (extract → clean → structure → boundaries → enrich → synthesize → validate) with Ollama |

### What's Broken or Missing

| Component | Status | What's Wrong |
|-----------|--------|--------------|
| **Auth** | Stub | `get_current_user_optional` returns None; `get_current_user_required` returns 401. No real login/register. |
| **Book requests / Wishlist** | Broken | `book_requests` table not in SQLite schema. Route requires auth (401). `request_service` has SQLite path but table doesn't exist. |
| **Multiple books** | Missing | Only 1 artifact (Metaphysics). Need 10–500 books processed through taxonomy pipeline. |
| **Production DB** | Missing | SQLite only. No Postgres/Supabase for production multi-user. |
| **Deployment** | Not deployed | `render.yaml` exists but never deployed. No artifact storage strategy for production. |
| **Brainrot reading** | Not built | New feature: word-by-word flash display of highlighted sections. |
| **User incentives** | Not built | No streaks, stats, or engagement hooks. |
| **Marketing** | Not started | No Reddit strategy, no landing page copy, no user acquisition plan. |

### Architecture (Current)

```
USER
 │
 ▼
┌──────────────────┐
│  FastAPI App      │
│  (port 5000)      │
└────────┬─────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌────────┐ ┌─────────────────┐
│ SQLite │ │ Artifact JSON   │
│        │ │ (filesystem)    │
│ tables:│ │                 │
│ users  │ │ metaphysics_    │
│ hl     │ │ aristotle.json  │
│ annot  │ │ (1 book)        │
│ chat   │ │                 │
└────────┘ └─────────────────┘
```

### Data Inventory

```
Artifacts:     1 (metaphysics_aristotle)
PDFs:          ~552 in batch1books/ (gitignored)
Extracted:     ~518 JSON (old regex-based, low quality)
DB tables:     users, highlights, annotations, chat_messages, schema_versions
Missing table: book_requests
Auth:          Stub (all users are "anon_test_user")
```

---

## 2. Desired State (Launch)

### What Must Work

| Component | Target | Details |
|-----------|--------|---------|
| **Books in library** | 10–500 | All processed through taxonomy pipeline with valid artifacts |
| **Ask → Route → Read** | Multi-book | Routes across the full library, not just Metaphysics |
| **Auth** | Real | Sign up, login, session, user-specific highlights/notes |
| **Highlights** | Per-user | Tied to real user_id, persist across devices |
| **Chat** | Real LLM | OpenAI or similar, grounded in passage, contextual |
| **Book requests** | Working | Users submit, admins manage, notifications on fulfillment |
| **Brainrot reading** | Shipped | Word-by-word flash at configurable WPM |
| **Deployment** | Live | Render.com or similar, Postgres, artifact storage |
| **Marketing** | Active | Reddit posts, user incentives, landing page |

### Architecture (Desired)

```
USER
 │
 ▼
┌──────────────────────────────────────┐
│  FastAPI App (deployed on Render)    │
│  - Real auth (Supabase Auth or JWT)  │
│  - LLM agents (OpenAI)              │
│  - Brainrot mode                     │
└────────┬─────────────────────────────┘
         │
    ┌────┴────────────┐
    │                 │
    ▼                 ▼
┌────────────┐ ┌─────────────────────────────┐
│ Postgres   │ │ Artifact Storage            │
│ (Supabase  │ │ (S3/bundled/CDN)            │
│  or Render │ │                             │
│  managed)  │ │ 10–500 artifact JSONs       │
│            │ │ Each: sections, themes,     │
│ tables:    │ │ summaries, routing_hints,   │
│ users      │ │ full text                   │
│ highlights │ │                             │
│ annotations│ └─────────────────────────────┘
│ chat_msgs  │
│ book_reqs  │
└────────────┘
```

### Gap Analysis

| Gap | From | To | Effort |
|-----|------|----|--------|
| Books | 1 artifact | 10–500 artifacts | High (pipeline batch run + review) |
| Auth | Stub | Real (Supabase/JWT) | Medium |
| DB | SQLite | Postgres | Medium (schema migration) |
| book_requests table | Missing | In schema | Low |
| Brainrot feature | Not built | JS word-flash + UI | Medium |
| Deployment | Local only | Render + Postgres + artifact storage | Medium |
| LLM agents | Mock mode | Real OpenAI calls | Low (already implemented, needs key) |
| Marketing | Nothing | Reddit + landing page | Low–Medium |
| Incentives | Nothing | Highlight stats, reading progress | Low |

---

## 3. The Path (Sequenced)

```
PHASE 0: Onboarding (Week 1)
│  Dev reads docs, runs app, runs pipeline on 1 book
│
PHASE 1: Taxonomy (Weeks 2–4)
│  Pipeline batch on all PDFs → 10–500 artifacts
│  Validate, flag, review
│
PHASE 2: Platform (Weeks 4–6)
│  Auth, book_requests table, user-tied data
│  Wishlist working end-to-end
│
PHASE 3: Brainrot (Weeks 6–7)
│  Design → implement → integrate
│
PHASE 4: Deploy (Weeks 7–9)
│  Artifact storage, Postgres, Render deploy
│  Routing optimization for large corpus
│
PHASE 5: Marketing (Weeks 9–10)
│  Landing page, Reddit, incentives
│
PHASE 6: Launch (Weeks 10–11)
│  Smoke tests, legal, soft launch, public launch
```

---

*This document is the source of truth for where we are and where we're going. Update it as reality changes.*
