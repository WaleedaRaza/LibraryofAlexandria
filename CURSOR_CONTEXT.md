# CURSOR CONTEXT — ALEXANDRIA LIBRARY (AUTHORITATIVE)

## READ THIS FIRST

This repository implements a **constrained, agent-guided reading system**.
It is **NOT** an AI chatbot, **NOT** a summary engine, and **NOT** a social platform.

If you (Cursor or human) introduce behavior that:
- Answers questions without routing to text
- Synthesizes ideas across books by default
- Mutates canonical text
- Adds recommendations, feeds, or virality

—you are violating the core design and **must stop**.

---

## 1. PRODUCT THESIS (NON-NEGOTIABLE)

> Users bring confusion or questions.  
> The system routes them to **primary source texts** (books, chapters, passages).  
> LLMs act only as **guides**, never as authorities.

**If a user can walk away without reading, the system has failed.**

---

## 2. WHAT THIS IS NOT

This app is explicitly **NOT**:
- ChatGPT with citations
- A PDF reader with AI
- A knowledge graph
- A recommendation engine
- A social reading app
- A content feed
- A place for "answers"

Any feature resembling the above is out of scope unless explicitly approved.

---

## 3. CORE CONSTRAINTS (THESE ARE THE MOAT)

### 3.1 Canon Is Sacred
- Books and text are immutable
- Users cannot edit or rewrite texts
- LLMs cannot modify canon
- `book_text.content` is the **single source of truth**
- `file_path` is admin-only; users never access PDFs directly

### 3.2 Reading Is Primary
- No default summaries
- No global chat
- No answer-first UI
- Everything resolves to text

### 3.3 LLMs Are Tools, Not Minds
- Stateless
- Deterministic
- Replaceable
- Constrained by contracts

If an LLM "feels smart," something is wrong.

---

## 4. AGENT ARCHITECTURE (LOCKED)

There are **exactly three agents in V1**.

### 4.1 Intent Classifier
**Purpose:** Map user input → conceptual domain  
**Forbidden:** answers, book selection, analysis

### 4.2 Reading Router
**Purpose:** Choose *where to read* from a pre-curated set  
**Forbidden:** summaries, conclusions, ideology

### 4.3 Text Companion
**Purpose:** Clarify only the selected text span  
**Forbidden:** general advice, modern extrapolation, cross-book synthesis

All agents:
- Must return structured outputs
- Must refuse when out of scope
- Must fail closed, not creatively

Agent contracts are defined in `app/agents/contracts.py` and **must be enforced**.

---

## 5. DATA MODEL INVARIANTS

### Canon Data (Global, Immutable)
- `books` - metadata only
- `book_text` - ONE full text per book (source of truth)
- `chapters` - offset references only, no text duplication

### User Data (Private, Mutable)
- `saved_books` - personal library
- `highlights` - offset-based, attached to chapters
- `annotations` - attached to highlights

### Growth Loop
- `book_requests` - users request books
- Admin approves and ingests
- Canon expands intentionally

There is **NO**:
- User-generated canon
- Community editing
- Automated ingestion

---

## 6. FILE STRUCTURE

```
alexandria/
├── app/
│   ├── routes/      # HTTP handlers (thin, declarative)
│   ├── services/    # Business logic (where work happens)
│   ├── agents/      # LLM wrappers (pure, stateless)
│   ├── domain/      # Entity logic (no DB calls)
│   └── db/          # Database layer
├── templates/       # Jinja2 templates
├── static/          # CSS, JS
└── admin/           # CLI tools (ingestion, validation)
```

Business logic lives in **services**, not routes.  
Agents **never** touch the database directly.

---

## 7. FORBIDDEN PATTERNS

Do **NOT**:
1. Add embeddings or vector search (not V1)
2. Add global chat or conversation history
3. Add "smart" recommendations
4. Inline business logic in routes
5. Let agents access the database
6. Create user-facing PDF access
7. Add social features (likes, shares, follows)
8. Add gamification (streaks, points, badges)
9. "Improve" the architecture without explicit approval

---

## 8. WHEN CURSOR SUGGESTS CHANGES

If Cursor asks:
> "Wouldn't it be better if…"

The answer is almost always **NO**.

This repo is intentionally *boring*. The constraint **is the product**.

Before accepting any diff, verify:
1. Does this preserve reading as the primary action?
2. Does this keep canon immutable?
3. Does this reduce LLM power rather than expand it?
4. Does this make future misuse harder?

If the answer is "no" to any of the above, **reject the change**.

---

## 9. CURRENT SPRINT SCOPE (V1)

### In Scope
- Ask → route → read
- Highlight + annotate
- Section-bound chat
- Personal library
- Wishlist / book requests

### Explicitly Deferred (NOT V1)
- Cross-book synthesis
- Shared annotations
- Recommendations
- Social features
- Personalization algorithms
- Vector search across full corpus
- OAuth (basic session auth only)
- User profiles

If something is not listed in "In Scope", do not implement it.

---

## 10. TECH STACK

| Component | Choice |
|-----------|--------|
| Backend | FastAPI |
| Database | SQLite (Postgres later) |
| Templates | Jinja2 (server-rendered) |
| Auth | Signed cookie sessions |
| LLM | OpenAI (mocked until ready) |
| Deploy | Vercel |

No changes to the stack without explicit approval.

---

*This document is the constitution. Obey it.*

