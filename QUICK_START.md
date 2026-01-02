# Alexandria - Quick Start

**READ THIS FIRST**, then dive into `ONBOARDING.md` for full details.

---

## What Is This?

**Alexandria = Wikipedia's lost opportunity for books**

- Users ask questions → Get routed to specific book passages
- Users request books → We curate and add for everyone
- Network effects: Every request grows the library

---

## Your Role

You're building the **foundation** (Phases 2-4) while Waleed aggregates 1300 books (Phase 1).

### Phase 2: Infrastructure (WEEKS 1-2) ← START HERE
- SQLite → Postgres migration
- Security: bcrypt, secure sessions, admin guards
- Deploy to production URL

### Phase 3: LLM Polish (WEEKS 3-4)
- Optimize agent prompts
- Error handling & rate limiting
- Cost control

### Phase 4: Launch Prep (WEEKS 5-6)
- Performance optimization
- Testing & security audit
- User experience polish

---

## The Rules (Never Break These)

1. **Discretion > Scale** - We curate and approve, not scrape
2. **Show the work** - Users see "Searching... Found 23 sources... Approved..."
3. **Fail closed** - "I don't know" > hallucination
4. **Canon is immutable** - Books stored once, chapters are offsets
5. **Check ownership** - Users can only touch their own data
6. **No magic** - Deterministic routing, manually curated taxonomy

---

## Run It Locally

```bash
cd alexandria
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create .env file
echo "SECRET_KEY=dev-secret-key-change-in-production" > .env
echo "USE_MOCK_AGENTS=true" >> .env

# Run it
uvicorn app.main:app --reload

# Open browser
open http://localhost:8000
```

---

## Key Files

```
alexandria/
├── ONBOARDING.md          ← Read this next (full context)
├── ARCHITECTURE.md        ← System design
├── ROADMAP.md            ← Detailed tasks
├── mockups/index.html    ← UI reference
├── app/
│   ├── main.py           ← Entry point
│   ├── routes/           ← HTTP endpoints
│   ├── agents/           ← Ask, Router, Companion
│   └── services/         ← Business logic
└── templates/            ← HTML
```

---

## Test the Agent System

```bash
# With mock agents (no API key needed)
USE_MOCK_AGENTS=true python test_taxonomy_artifacts.py

# With OpenAI (if you have a key)
USE_MOCK_AGENTS=false OPENAI_API_KEY="sk-..." python test_taxonomy_artifacts.py
```

---

## First Day Checklist

- [ ] Read this file
- [ ] Read `ONBOARDING.md`
- [ ] Run app locally
- [ ] Browse mockups (`mockups/index.html`)
- [ ] Test agent system
- [ ] Read `ARCHITECTURE.md`
- [ ] Sync with Waleed

---

## Week 1 Goal

**Production URL live with secure auth**

- [ ] Supabase set up
- [ ] Database migrated to Postgres
- [ ] Bcrypt passwords
- [ ] Secure sessions
- [ ] Deploy to Render/Fly.io
- [ ] Health checks working

---

## The Vision

If we execute:
- **Network effects** - Every user grows the library
- **First mover** - No one else doing curated, transparent aggregation  
- **Post-.com opportunity** - Wikipedia couldn't, we can
- **The shovel** - Infrastructure for knowledge seekers

This only works if the foundation is solid. **That's your job.**

---

**Next**: Read `ONBOARDING.md` for the full picture.
