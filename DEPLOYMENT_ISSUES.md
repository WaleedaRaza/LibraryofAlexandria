# Deployment Issues — Alexandria Library

> 34 issues, 7 phases, from onboarding to public launch. Each becomes a GitHub issue.

---

## Phase 0: Codebase Mastery (Week 1)

### 0.1 — Read and summarize all core documentation
Read NEW_DEV_PRESENTATION.md, manifest.md, taxonomy.md, ARCHITECTURE.md, CURRENT_VS_DESIRED_STATE.md. Produce a 1-page internal summary.

**Acceptance criteria:**
- Summary document in docs/
- Can explain Ask → Route → Read in 2 minutes
- Knows which files handle routing, highlights, artifacts

### 0.2 — Run app locally and complete full user flow
Get app running. Ask a question → routing results → reader → highlight → chat. Confirm highlights persist.

**Acceptance criteria:**
- uvicorn runs, full flow works
- Highlights survive reload
- Setup gotchas documented in docs/SETUP.md

### 0.3 — Run taxonomy pipeline on a single test PDF
Process one book with Ollama. Inspect artifact. Verify sections, summaries, themes.

**Acceptance criteria:**
- Artifact produced, inspected, section text readable
- Document: model used, time per book

### 0.4 — Map PDF corpus and ingestion path
Locate ~500 PDFs. Plan batch input. Note duplicates.

**Acceptance criteria:**
- PDF inventory documented
- Duplicate handling plan
- batch1books → taxonomy-pipeline/data/pdfs/ path clear

---

## Phase 1: Taxonomy — Full Corpus (Weeks 2–4)

### 1.1 — Configure taxonomy batch for full corpus
Set up batch processing with resume, failure logging, progress.

**Acceptance criteria:**
- Batch command works against full PDF dir
- Skips completed books
- Logs failures

### 1.2 — Run taxonomy pipeline on all ~500 books
Full batch. Expect 17–24 hours. Use checkpoint/resume.

**Acceptance criteria:**
- All books processed or explicitly failed
- Summary: success, failure, low-confidence counts

### 1.3 — Validate and flag low-confidence artifacts
Score artifacts. Create flagged manifest.

**Acceptance criteria:**
- Validation scores all artifacts
- Low-confidence listed in _flagged.json
- Review workflow documented

### 1.4 — Organize artifact output and naming
Normalize book_id, file names. Ensure artifact_loader discovers all.

**Acceptance criteria:**
- Consistent naming (e.g. title__author.json)
- get_available_books() returns full library
- No duplicates or broken paths

### 1.5 — Human review of flagged books
Process flagged artifacts. Re-run or manual fix.

**Acceptance criteria:**
- All flagged books reviewed
- Decisions recorded
- Re-runs completed

### 1.6 — Routing quality check across genres
Test 20+ diverse queries. Verify multi-book, multi-genre routing.

**Acceptance criteria:**
- 20+ test queries documented with expected vs actual
- Routing shows variety
- Edge cases documented

---

## Phase 2: Platform Core (Weeks 4–6)

### 2.1 — Add book_requests table to SQLite schema
Add migration or update schema.sql. Match request_service expectations.

**Acceptance criteria:**
- book_requests table exists in SQLite
- Columns: id, user_id, title, author, reason, status, admin_notes, created_at, resolved_at
- request_service works in SQLite mode

### 2.2 — Replace stub auth with real authentication
Implement sign up, login, logout, session. Supabase Auth or JWT.

**Acceptance criteria:**
- Sign up and login work
- Session persists across requests
- get_current_user_optional and get_current_user_required use real auth
- Guest flow still works

### 2.3 — Tie highlights, annotations, chat to real user_id
Highlights persist per user. No cross-user leakage.

**Acceptance criteria:**
- Logged-in user's data tied to their account
- Guest users: read-only or ephemeral
- No data leakage between users

### 2.4 — Make wishlist/book requests work end-to-end
Users submit requests. Admins manage queue.

**Acceptance criteria:**
- User submits request (title, author, reason)
- User sees their requests and status
- Admin can approve/decline
- Statuses: PENDING, APPROVED, DECLINED, ADDED

### 2.5 — Notify users when requested book is added
When admin marks request as ADDED, notify requester.

**Acceptance criteria:**
- Notification mechanism (email or in-app)
- Admin triggers notification on fulfillment

---

## Phase 3: Brainrot Reading (Weeks 6–7)

### 3.1 — Design Brainrot Reading UI/UX
User highlights large section → words flash at configurable WPM. Design flow, layout, controls.

**Acceptance criteria:**
- Written spec or wireframe
- Entry point defined (e.g. button on highlight menu)
- Speed control (200–600+ WPM), pause/resume

### 3.2 — Implement word-by-word flash display
Core JS: split text into words, render one at a time, configurable interval.

**Acceptance criteria:**
- Words display centered, one at a time
- Speed slider or input
- Pause/Resume
- Desktop and mobile

### 3.3 — Integrate Brainrot into reader highlight flow
"Brainrot" action on highlight → opens flash view with that text.

**Acceptance criteria:**
- Action available on highlight menu/sidebar
- Opens Brainrot mode with selected text
- Return to normal reading
- 500+ word selections work smoothly

### 3.4 — Persist Brainrot preferences
Save preferred speed for future sessions.

**Acceptance criteria:**
- Speed stored (localStorage or user settings)
- Restored on next session

---

## Phase 4: Deployment (Weeks 7–9)

### 4.1 — Decide artifact storage for production
500 JSONs need serving. Options: bundle with app, S3, CDN, DB.

**Acceptance criteria:**
- Decision documented with rationale
- artifact_loader compatible with chosen storage
- Cost/latency considered

### 4.2 — Support configurable artifact path
Make artifact directory configurable via env var.

**Acceptance criteria:**
- ARTIFACT_DIR env var or config
- Works locally and deployed
- Docs updated

### 4.3 — Migrate SQLite to Postgres for production
Production DB with schema migration.

**Acceptance criteria:**
- Postgres schema matches SQLite semantics
- Migration script or steps documented
- App works with DATABASE_URL pointing to Postgres

### 4.4 — Deploy to Render (or chosen provider)
Live deployment with env vars, health check.

**Acceptance criteria:**
- App deployed, /health returns 200
- Full flow works in production
- Env vars documented

### 4.5 — Optimize routing for large corpus
Candidate filtering, caching, acceptable latency (<5s).

**Acceptance criteria:**
- No full-scan of all sections per query
- Latency acceptable
- Cache for repeated queries

### 4.6 — Add basic monitoring and error tracking
Structured logs, optional Sentry.

**Acceptance criteria:**
- 500s traceable
- Request correlation in logs
- Optional: Sentry or similar

---

## Phase 5: Marketing & User Acquisition (Weeks 9–10)

### 5.1 — Landing page and value proposition
Clear headline, benefits, CTA.

**Acceptance criteria:**
- Headline + 2–3 benefit bullets
- CTA to try the app
- Mobile-friendly

### 5.2 — Reddit launch strategy and post templates
Target subreddits, draft posts, schedule.

**Acceptance criteria:**
- Subreddit list: r/books, r/philosophy, r/Meditation, r/stoicism, r/literature, etc.
- 2–3 post variants
- Schedule and guidelines (no spam)

### 5.3 — User incentive design
What brings users back: highlight counts, reading progress, streaks.

**Acceptance criteria:**
- Ideas documented
- 2–3 picked for V1
- UI placement defined

### 5.4 — Implement first user incentives
Ship chosen incentives.

**Acceptance criteria:**
- At least one incentive live and visible
- Doesn't conflict with "reading first" mission

### 5.5 — Analytics baseline
Track key events: ask, route, read, highlight, chat, brainrot.

**Acceptance criteria:**
- Core events tracked
- Privacy-preserving
- No PII without consent

---

## Phase 6: Launch (Weeks 10–11)

### 6.1 — Smoke test suite for production
Document or automate critical path tests.

**Acceptance criteria:**
- Smoke test checklist or script
- All critical paths pass
- Part of release process

### 6.2 — Legal and terms (minimal)
Terms of Service, Privacy Policy. Cover data, copyright.

**Acceptance criteria:**
- Terms and Privacy links on site
- Appropriate for public-domain books
- Contact mechanism

### 6.3 — Soft launch and feedback loop
Small group launch. Feedback channel.

**Acceptance criteria:**
- 10–20 users onboarded
- Feedback mechanism live
- Learnings documented

### 6.4 — Public launch
Execute launch. Reddit posts. Monitor.

**Acceptance criteria:**
- Launch executed per strategy
- Monitoring active
- Post-launch fix list started

---

## Summary

| Phase | Issues | Timeline |
|-------|--------|----------|
| 0: Mastery | 4 | Week 1 |
| 1: Taxonomy | 6 | Weeks 2–4 |
| 2: Platform | 5 | Weeks 4–6 |
| 3: Brainrot | 4 | Weeks 6–7 |
| 4: Deploy | 6 | Weeks 7–9 |
| 5: Marketing | 5 | Weeks 9–10 |
| 6: Launch | 4 | Weeks 10–11 |
| **Total** | **34** | **~11 weeks** |
