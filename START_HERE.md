# 👋 Welcome to Alexandria

## Read These (In Order)

1. **This file** (1 min) - You are here
2. [`QUICK_START.md`](./QUICK_START.md) (5 min) - Quick overview
3. [`ONBOARDING.md`](./ONBOARDING.md) (20 min) - Full context
4. [`PHASE2_CHECKLIST.md`](./PHASE2_CHECKLIST.md) (bookmark this) - Your daily reference

## What We're Building

**Alexandria = The Wikipedia moment for books that Wikipedia never captured**

- Users ask questions → Get specific book passages
- Users request books → We curate and add for everyone  
- Every request grows the library → Network effects = exponential value

## Your Mission

Build the foundation (Phases 2-4) while Waleed aggregates 1300 books (Phase 1).

**6 weeks to launch:**
- Weeks 1-2: Infrastructure & Auth (Postgres, security, deployment)
- Weeks 3-4: LLM & Agent hardening (prompts, costs, reliability)
- Weeks 5-6: Polish & launch prep (testing, security audit, UX)

## Run It Now

```bash
cd alexandria
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create .env
echo "SECRET_KEY=dev-secret-key" > .env
echo "USE_MOCK_AGENTS=true" >> .env

# Run it
uvicorn app.main:app --reload

# Open browser
open http://localhost:8000
```

## The Rules (Never Break)

1. **Discretion > Scale** - We curate, not scrape
2. **Show the work** - Users see the process happening
3. **Fail closed** - "I don't know" > hallucination
4. **Check ownership** - Users can only touch their own data

## Day 1 Goals

- [ ] Run app locally
- [ ] Read all onboarding docs
- [ ] Browse mockups (`mockups/index.html`)
- [ ] Sync with Waleed
- [ ] Set up Supabase project

## The Opportunity

If we execute:
- **Network effects** - Every user grows the library
- **First mover** - No one else doing this right
- **Post-.com world** - Wikipedia couldn't, we can
- **The shovel** - Infrastructure for the AI knowledge era

**This only works if the foundation is solid. That's your job.**

---

**Next**: Open [`QUICK_START.md`](./QUICK_START.md)
