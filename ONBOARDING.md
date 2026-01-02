# 🏛️ Alexandria Library - Developer Onboarding

**Welcome.** You're joining at a critical phase. This document will get you oriented quickly.

---

## What We're Building

**Alexandria is the Wikipedia moment for books that Wikipedia never captured.**

### The Core Idea

1. **Users ask questions** → Get routed to specific book chapters that answer them
2. **Users request books** → We find, curate, and add them to the library for everyone
3. **Every request grows the library** → Network effects make it exponentially more valuable

### The Legal Strategy

We're **aggregators and middlemen** operating in a post-.com world. The key:
- **Discretion** - We curate and approve, not scrape and dump
- **Fair use framing** - Users request, we facilitate research access
- **User pipeline transparency** - Show the work happening (builds trust + legal cover)

### The Vision

A platform where **every book you want** is available:
- View it as a PDF in our library
- Download it for offline reading
- Or request it and we'll add it for everyone

If done right, this becomes **the shovel during the gold rush** - aggregating knowledge that others can't or won't.

---

## Current State (January 2026)

### ✅ What's Working

**Agent System (The Brain)**
- Ask Agent: Classifies user questions into domains
- Reading Router: Maps questions to specific book chapters via taxonomy
- Text Companion: Answers questions about selected text
- 193 books indexed across 6 domains (Philosophy, Strategy, Psychology, Tech, Economics, Business)
- Artifact-based routing (no embeddings, deterministic, fast)

**Core Features**
- User can browse library, read books
- Reading interface with chapter navigation
- Highlight and annotation system (UI exists, persistence works)
- Book request/wishlist system
- Admin approval queue

**Infrastructure**
- FastAPI + Python backend
- SQLite database (works for dev, needs Postgres for prod)
- Jinja2 templates with custom CSS
- Agent system with mock mode (works without OpenAI)

### 🔶 What's In Progress

**Book Aggregation Pipeline**
- We're aggregating the full 1300 books from our curated list
- Discovery, scoring, and ingestion systems built
- Admin tooling partially complete

### ⬜ What's Not Done Yet

**Production Infrastructure**
- Auth is basic (needs bcrypt, secure sessions)
- Database is SQLite (needs Postgres)
- No deployment setup
- No error monitoring

**LLM Polish**
- System prompts are functional but not optimized
- Agent coordination could be tighter
- Rate limiting is basic

**Hardening**
- Security audit needed
- Performance testing needed
- Error handling is inconsistent
- No comprehensive testing

---

## The Roadmap - Your Mission

We're executing in 4 clear phases. **Your work determines if we launch.**

### Phase 1: Complete Book Aggregation (CURRENT - Don't Worry About It)

**Status**: Waleed is handling this
**Goal**: Get all 1300 books ingested and indexed
**Your role**: None right now, focus on the next phases

### Phase 2: Infrastructure & Auth (WEEKS 1-2 - YOUR PRIORITY)

**Goal**: Make it production-ready

**Database Migration**
- [ ] Migrate from SQLite to Postgres (Supabase)
- [ ] Update connection handling for pooling
- [ ] Verify all queries work on Postgres
- [ ] Set up connection string management

**Authentication & Security**
- [ ] Replace SHA256 with bcrypt for passwords
- [ ] Implement secure session management
- [ ] Add `HttpOnly`, `Secure`, `SameSite` cookie flags
- [ ] Build proper admin role checks (`require_admin` dependency)
- [ ] Add CSRF protection for mutations

**Environment Management**
- [ ] Proper env var validation on startup
- [ ] Fail gracefully with clear messages
- [ ] Force mock mode if no OpenAI key
- [ ] Health check endpoint for monitoring

**Deployment Setup**
- [ ] Configure Render or Fly.io
- [ ] Set up CI/CD pipeline
- [ ] Static asset optimization
- [ ] Error tracking (Sentry or similar)

**Exit Criteria**: Can deploy to production URL, users can register/login securely, admin routes are protected.

---

### Phase 3: LLM & Agent Hardening (WEEKS 3-4)

**Goal**: Make the agent system bulletproof

**System Prompting**
- [ ] Review and optimize all agent prompts
- [ ] Add clear constraints and examples
- [ ] Implement proper few-shot examples
- [ ] Test edge cases (vague questions, off-topic, etc.)

**Agent Coordination**
- [ ] Ensure proper error propagation
- [ ] Add retry logic with backoff
- [ ] Implement circuit breakers
- [ ] Better logging/observability for agent decisions

**Rate Limiting & Costs**
- [ ] Per-user rate limiting
- [ ] Cost tracking for OpenAI calls
- [ ] Fallback strategies when rate limited
- [ ] Mock mode parity (mock responses should be realistic)

**Taxonomy Improvement**
- [ ] Review domain classifications
- [ ] Fix misclassified books
- [ ] Expand subdomains where needed
- [ ] Verify routing accuracy with test queries

**Exit Criteria**: Agent system handles edge cases gracefully, costs are controlled, routing is reliable, users trust the recommendations.

---

### Phase 4: Hardening for Launch (WEEKS 5-6)

**Goal**: Ready for real users

**Performance**
- [ ] Add database indexes
- [ ] Eliminate N+1 queries
- [ ] Page load targets: <2s homepage, <3s library, <2s reader
- [ ] Test with 1000+ books in DB

**Error Handling**
- [ ] All errors show friendly messages (never stack traces)
- [ ] Proper 404/500 pages
- [ ] Empty states for all views
- [ ] Loading states for all async operations

**Testing**
- [ ] Write smoke tests for critical paths
- [ ] Test user registration → browse → read → highlight flow
- [ ] Test admin approval → ingestion flow
- [ ] Test agent routing with 50+ diverse questions

**Security Audit**
- [ ] Verify all user data operations check ownership
- [ ] Check for SQL injection vectors
- [ ] Verify XSS protection
- [ ] CSRF on all mutations
- [ ] Secrets not in logs or error messages

**User Experience Polish**
- [ ] Status updates for book requests (show the work happening)
- [ ] Confirmation messages for all actions
- [ ] Mobile-friendly reader
- [ ] Keyboard shortcuts where useful

**Documentation**
- [ ] Admin workflow guide
- [ ] Developer setup guide
- [ ] API documentation
- [ ] Known issues and workarounds

**Exit Criteria**: Smoke tests pass, no launch blockers, feels polished, ready to share URL with real users.

---

## Key Principles (The Golden Path)

These are non-negotiable. If you violate these, the architecture breaks:

### 1. **Discretion Over Scale**
We're not trying to be Sci-Hub. We curate. We approve. We show the work. This is legal cover AND UX.

### 2. **Show Users the Process**
When a user requests a book, they see:
- "Searching 15 sources..."
- "Found 23 candidates..."
- "Under human review..."
- "Approved! Retrieving..."

This transparency is critical. It shows value and covers us legally.

### 3. **Fail Closed**
If an agent can't answer confidently, it says "I don't know" instead of making something up. We route to books we have, never hallucinate book content.

### 4. **The Canon is Immutable**
Book text lives in `book_text` once. Chapters are offsets, never duplicates. This keeps the system simple and fast.

### 5. **User Data is Owned**
Highlights, annotations, saved books - users own their data. Check ownership on EVERY mutation.

### 6. **No Magic**
The taxonomy is curated manually. Routing is deterministic. We don't use embeddings or vector search. This keeps it debuggable and predictable.

### 7. **The Foundation Before Features**
We're building infrastructure first (Phase 2), then LLM polish (Phase 3), then hardening (Phase 4). No skipping phases.

---

## Getting Started

### Your First Day

1. **Read these docs** (in order):
   - `ONBOARDING.md` (this file)
   - `ARCHITECTURE.md` (understand the layers)
   - `ROADMAP.md` (see the detailed task breakdown)
   - `QUICKSTART_ARTIFACTS.md` (understand the agent system)

2. **Check out the mockups**:
   ```bash
   cd alexandria/mockups
   open index.html
   ```
   These show the intended UX. Compare to what's live.

3. **Run the app locally**:
   ```bash
   cd alexandria
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   
   # Create .env file (see .env.example)
   # Minimum: SECRET_KEY, USE_MOCK_AGENTS=true
   
   uvicorn app.main:app --reload
   ```
   Open `http://localhost:8000`

4. **Test the agent system**:
   ```bash
   # Run with mock agents (no API key needed)
   USE_MOCK_AGENTS=true python test_taxonomy_artifacts.py
   ```

5. **Explore the codebase**:
   - `app/main.py` - Entry point, route registration
   - `app/routes/` - All HTTP endpoints
   - `app/agents/` - The three agents (Ask, Router, Companion)
   - `app/services/` - Business logic layer
   - `app/db/` - Database schema and helpers
   - `templates/` - Jinja2 HTML templates
   - `static/` - CSS and client JS

### Your First Week

**Goal**: Own Phase 2 (Infrastructure & Auth)

1. **Set up Supabase** (Day 1)
   - Create project
   - Get connection string
   - Apply schema from `app/db/schema.sql`

2. **Migrate to Postgres** (Days 1-2)
   - Update `database.py` for Postgres
   - Test all queries
   - Verify app boots and works

3. **Security Baseline** (Days 3-4)
   - Implement bcrypt for passwords
   - Secure session cookies
   - Admin role checks
   - CSRF protection

4. **Deployment** (Day 5)
   - Set up Render/Fly.io
   - Configure env vars
   - Deploy and verify
   - Set up health checks

### Your Second Week

**Goal**: Finish Phase 2, start Phase 3

1. **Error handling** (Days 6-7)
   - Friendly error pages
   - Proper logging
   - Error tracking setup

2. **Start LLM work** (Days 8-10)
   - Review agent prompts
   - Test edge cases
   - Optimize system messages

---

## Communication & Coordination

### With Waleed

- He's focused on book aggregation (Phase 1)
- You own Phases 2-4
- Daily sync: What's blocked, what's done, what's next
- Use this doc as the source of truth for roadmap

### Decision Making

- **Small decisions**: Just do it (code style, variable names, etc.)
- **Medium decisions**: Document in PR, Waleed reviews async
- **Big decisions**: Sync discussion required (architecture changes, tech choices)

### What Success Looks Like

**Week 2**: Production URL is live, users can register/login securely
**Week 4**: Agent system is bulletproof, costs are controlled
**Week 6**: App feels polished, ready for real users

---

## Important Files Quick Reference

```
alexandria/
├── ONBOARDING.md          ← You are here
├── ARCHITECTURE.md        ← System design, layers, invariants
├── ROADMAP.md            ← Detailed task breakdown by phase
├── QUICKSTART_ARTIFACTS.md ← How the agent system works
├── app/
│   ├── main.py           ← FastAPI entry point
│   ├── routes/           ← HTTP endpoints
│   │   ├── pages.py      ← Homepage, about, etc.
│   │   ├── ask.py        ← Question routing
│   │   ├── reader.py     ← Reading interface
│   │   ├── library.py    ← Browse books
│   │   ├── wishlist.py   ← Book requests
│   │   ├── auth.py       ← Login/register
│   │   └── admin.py      ← Admin approval queue
│   ├── agents/           ← The three agents
│   │   ├── ask_agent.py
│   │   ├── reading_router.py
│   │   └── text_companion.py
│   ├── services/         ← Business logic
│   ├── db/              ← Database schema & helpers
│   └── config.py        ← Settings management
├── templates/           ← Jinja2 HTML
├── static/             ← CSS, fonts, images
├── mockups/            ← UI reference (open index.html)
└── artifacts/          ← Agent routing data
    ├── taxonomy.v1.json
    ├── book_index.v1.json
    └── chapter_index.v1.json
```

---

## The Opportunity

If we execute this well:

1. **Network effects**: Every user request makes it more valuable
2. **First mover advantage**: No one else is doing curated, transparent book aggregation
3. **Post-.com world**: Wikipedia couldn't, but we can (different model)
4. **The shovel**: We're infrastructure for knowledge seekers

This only works if the foundation is solid. That's Phase 2. That's your job.

**Let's build.**

---

**Questions?** Ask Waleed. Update this doc as you learn.

**Last Updated**: January 1, 2026
