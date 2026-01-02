# Alexandria Roadmap (Production Launch)

> **See `ARCHITECTURE.md` for complete system design and invariants.**
> **See `SMOKE_TESTS.md` for verification checklists.**

---

## North Star

**Deployed Alexandria** where:

- Users can **ask questions** and get routed to specific passages
- Users can **read, highlight, annotate** and their work persists
- Users can **request books** and see the status
- Admins can **approve requests** and **ingest books** via web UI
- The **canon grows** through a curated pipeline
- The platform is **secure enough for strangers** (bcrypt, secure cookies, admin guards)
- Everything runs on **real infrastructure** (Postgres + Render/Fly.io)

---

## What "Complete" Means

Every feature must satisfy ALL of:

| Criterion | Question to Ask |
|-----------|-----------------|
| **Write Path** | Can the user create/update this thing? |
| **Read Path** | Does it persist and display after reload? |
| **Permissions** | Are unauthorized users blocked? |
| **Validation** | Does bad input show a helpful error? |
| **Empty State** | What shows when there's no data? |
| **Loading State** | What shows during async operations? |
| **Error State** | What happens when things fail? |
| **Smoke Test** | Can we manually verify this works? |

If ANY criterion is missing, the feature is **incomplete**.

---

## Phase 1: Infrastructure Foundation

**Goal**: App runs on real infrastructure with real persistence.
**Duration**: Days 1-2
**Blocking**: Cannot deploy without this.

### M1.1: Database Migration to Postgres

**What "complete" means:**
- [ ] Supabase project provisioned
- [ ] `DATABASE_URL` connection string obtained
- [ ] Schema applied to Postgres (all 10 tables)
- [ ] `database.py` updated to handle Postgres connections
- [ ] Connection pooling configured (or using Supabase's)
- [ ] All SQL is Postgres-compatible (no SQLite-only syntax)
- [ ] App boots and connects successfully
- [ ] All 22 endpoints work against Postgres

**Verification:**
```bash
# Register user → check users table in Supabase
# Browse library → verify books load
# Create highlight → verify highlights table updated
```

---

### M1.2: Security Baseline

**What "complete" means:**
- [ ] `bcrypt` added to requirements.txt (latest version)
- [ ] `hash_password()` uses bcrypt with cost factor 12
- [ ] `verify_password()` uses bcrypt verify
- [ ] Existing users: Migration path documented (or fresh start)
- [ ] Cookie `secure=True` when `ENV=production`
- [ ] Cookie `httponly=True` always (already done)
- [ ] Cookie `samesite="lax"` always (already done)
- [ ] `role` field exists on users (already in schema)
- [ ] `require_admin` dependency created
- [ ] All future `/admin/*` routes use `require_admin`

**Verification:**
```bash
# Register new user → check password_hash in DB starts with $2b$
# Login → check cookie in browser dev tools has Secure flag (in prod)
# Access admin route as user → get 403
```

---

### M1.3: Environment Validation

**What "complete" means:**
- [ ] Startup checks for `DATABASE_URL` → fail with clear message if missing
- [ ] Startup checks for `SESSION_SECRET` → fail with clear message if missing  
- [ ] If `OPENAI_API_KEY` missing → force `USE_MOCK_AGENTS=true`, log warning
- [ ] If `ENV=production` but `DEBUG=true` → log warning
- [ ] Health endpoint at `/health` returns:
  - `{"status": "ok", "db": "connected"}` when healthy
  - `{"status": "error", "db": "disconnected"}` when DB down

**Verification:**
```bash
# Start with no DATABASE_URL → clear error
# Start with no OPENAI_API_KEY → app runs in mock mode
# Hit /health → get JSON response
```

---

### M1.4: Deploy to Render

**What "complete" means:**
- [ ] `render.yaml` or manual service created
- [ ] Environment variables configured:
  - `DATABASE_URL` (Supabase)
  - `SESSION_SECRET` (generated)
  - `ENV=production`
  - `OPENAI_API_KEY` (optional)
- [ ] Build command: `pip install -r requirements.txt`
- [ ] Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- [ ] Static files serving verified
- [ ] Health check configured on `/health`
- [ ] Auto-deploy on push to main (optional for now)

**Verification:**
```bash
# Visit production URL → homepage loads
# Register account → login works
# Browse library → books display with CSS
```

---

### Phase 1 Exit Criteria

- [ ] Production URL is accessible
- [ ] Can register, login, logout
- [ ] Can browse library
- [ ] Can read books
- [ ] Health endpoint returns 200
- [ ] Passwords are bcrypt in DB
- [ ] No crashes when OPENAI_API_KEY missing

---

## Phase 2: User Feature Completion

**Goal**: Every user feature works end-to-end with proper feedback.
**Duration**: Days 3-4
**Blocking**: UX is broken without this.

### M2.1: Highlight Persistence & Display

**What "complete" means:**
- [ ] `GET /read/{id}` loads user's highlights for current chapter
- [ ] Highlights passed to template as list with:
  - `id`, `start_offset`, `end_offset`, `color`, `created_at`
  - `text_snippet` (first 80 chars of highlighted text)
- [ ] Annotations rail shows each highlight:
  - Quoted snippet in italics
  - Color indicator
  - Timestamp
  - "Add note" button (if no annotation)
- [ ] Click highlight in rail → (future: scroll to position)
- [ ] Delete button removes highlight from DB and UI
- [ ] Anonymous users see empty rail with login prompt

**Technical approach:**
1. In `reader.py`, query highlights after getting chapter text
2. For each highlight, extract snippet using offsets
3. Pass to template
4. Template renders in annotations rail

**Verification:**
```bash
# Login → Read book → Highlight text
# Refresh page → highlight visible in rail
# Delete highlight → refresh → gone
```

---

### M2.2: Annotation Persistence & Display

**What "complete" means:**
- [ ] When loading highlights, also load associated annotations
- [ ] Each highlight card shows annotation if exists
- [ ] "Add note" on highlight opens inline editor
- [ ] Save note → POST to `/read/{id}/annotation` → updates UI
- [ ] Edit note → same flow
- [ ] Delete note → DELETE request → updates UI
- [ ] Permission: only owner can CRUD

**Verification:**
```bash
# Create highlight → add note → refresh → note visible
# Edit note → refresh → changes persist
# Delete note → refresh → gone
# Delete highlight → annotation also gone (cascade)
```

---

### M2.3: Chat Polish

**What "complete" means:**
- [ ] Chat panel shows loading spinner during LLM call
- [ ] Response appears with smooth transition
- [ ] Error shows friendly message (not stack trace)
- [ ] Rate limit exceeded → clear message with wait time
- [ ] Constraint reminder visible: "I only explain the selected text..."
- [ ] Mock mode response is realistic (not just "Mock response")

**Verification:**
```bash
# Select text → ask question → see loading → see response
# Spam chat → hit rate limit → see friendly error
# Remove OPENAI_API_KEY → mock response still makes sense
```

---

### M2.4: Empty & Error States

**What "complete" means:**
- [ ] Library with no books → "No books yet" message
- [ ] Library search with no results → "No books match" message
- [ ] My Library empty → "Save books to see them here" prompt
- [ ] Wishlist empty → "No requests yet" + prompt to request
- [ ] Routing with no results → "I couldn't find relevant reading" + browse suggestion
- [ ] Reader with failed book load → 404 page
- [ ] Any 500 error → friendly 500 page (never stack trace)

**Verification:**
```bash
# New user → My Library → see empty state
# Search "zzzzzz" → see no results message
# Invalid book ID → see 404
```

---

### M2.5: Loading States

**What "complete" means:**
- [ ] Ask form shows spinner/disabled state during routing
- [ ] Save book button shows "Saving..." during request
- [ ] Highlight creation shows brief flash or confirmation
- [ ] Chat shows "Thinking..." during LLM call
- [ ] Any button that triggers async → disabled during request

**Technical approach:**
- Add loading classes in JS
- Disable buttons during fetch
- Show inline spinners or text changes

**Verification:**
```bash
# Click Save → see brief loading state → see confirmation
# Ask question → see loading → see results
```

---

### Phase 2 Exit Criteria

- [ ] Highlights persist and display after reload
- [ ] Annotations persist and display after reload
- [ ] Chat shows loading and handles errors gracefully
- [ ] All empty states have helpful messages
- [ ] All async operations show loading feedback
- [ ] User can complete full loop without confusion

---

## Phase 3: Admin Operations

**Goal**: Admin can manage the platform without CLI.
**Duration**: Days 4-5
**Blocking**: Ops burden without this.

### M3.1: Admin Route Guard

**What "complete" means:**
- [ ] `require_admin` dependency checks `user.role == 'admin'`
- [ ] Non-admin → 403 Forbidden with friendly page
- [ ] Not logged in → redirect to login
- [ ] All `/admin/*` routes use this guard
- [ ] At least one admin user exists (seeded or created manually)

**Verification:**
```bash
# Login as regular user → go to /admin/requests → see 403
# Login as admin → go to /admin/requests → see page
```

---

### M3.2: Request List Page

**What "complete" means:**
- [ ] Route: `GET /admin/requests`
- [ ] Shows all book requests in table/list
- [ ] Columns: Title, Author, User email, Status, Submitted date
- [ ] Filter tabs/buttons: All, Pending, Approved, Rejected, Added
- [ ] Click row → goes to detail page
- [ ] Pending count shown prominently
- [ ] Pagination if >50 requests (or defer)

**Template**: `templates/admin/requests.html`

**Verification:**
```bash
# Have 5 requests in different statuses
# View page → see all
# Click Pending → see only pending
# Click row → go to detail
```

---

### M3.3: Request Detail & Actions

**What "complete" means:**
- [ ] Route: `GET /admin/requests/{id}`
- [ ] Shows: Title, Author, User email, Reason, Status, Dates
- [ ] Action buttons based on status:
  - Pending: [Approve] [Reject]
  - Approved: [Mark as Added]
  - Rejected: (no actions)
  - Added: (no actions)
- [ ] Approve → optional admin note → status = APPROVED
- [ ] Reject → required admin note → status = REJECTED
- [ ] Mark Added → status = ADDED, resolved_at = now
- [ ] Redirect to list after action

**Routes:**
- `POST /admin/requests/{id}/approve`
- `POST /admin/requests/{id}/reject`
- `POST /admin/requests/{id}/mark-added`

**Verification:**
```bash
# View pending request → click Approve → redirected to list
# Check status in list → shows APPROVED
# View rejected request → no action buttons
```

---

### M3.4: User Status Visibility

**What "complete" means:**
- [ ] User's wishlist shows current status for each request
- [ ] Status badge color-coded:
  - Pending: yellow/orange
  - Approved: blue
  - Rejected: red
  - Added: green
- [ ] If rejected, show admin note
- [ ] If added, show "Now available" with link to book (future)

**Verification:**
```bash
# Submit request as user
# Approve as admin
# Check user's wishlist → status updated
```

---

### Phase 3 Exit Criteria

- [ ] Admin routes are protected
- [ ] Admin can view all requests
- [ ] Admin can approve, reject, mark added
- [ ] User sees status updates on wishlist
- [ ] At least one admin account exists

---

## Phase 4: Canon Quality

**Goal**: The library is clean and properly categorized.
**Duration**: Days 5-6
**Blocking**: UX quality, routing accuracy.

### M4.1: Deduplication

**What "complete" means:**
- [ ] Script to identify duplicates (same title, similar author)
- [ ] Strategy: keep book with most text / best metadata
- [ ] Delete duplicates from books, book_text, chapters tables
- [ ] Rebuild artifacts after cleanup
- [ ] Unique constraint added to prevent future dupes
- [ ] Ingestion updated to check for existing before insert

**Current state**: 193 books, many duplicates (e.g., 7x "A Mind at Play")
**Target state**: ~80-100 unique books

**Verification:**
```bash
# Run dedup script → see "Removed X duplicates"
# Check book count → reduced
# Rebuild artifacts → no errors
# Browse library → no "(1)" "(2)" suffixes
```

---

### M4.2: Chapter Detection Improvement

**What "complete" means:**
- [ ] For key books, define chapters manually OR
- [ ] Improve heuristics (detect "Chapter X" patterns)
- [ ] At minimum: Top 20 books have real chapters
- [ ] Fallback: "Full Text" is acceptable for others
- [ ] Chapters table updated with meaningful titles

**Verification:**
```bash
# Open Meditations → see multiple chapters
# Open Art of War → see chapters by section
```

---

### M4.3: Domain Refinement

**What "complete" means:**
- [ ] Review all books' domain assignments
- [ ] Fix obvious misclassifications (e.g., Black Hat Python under Philosophy)
- [ ] Add subdomain where meaningful
- [ ] Update DB and rebuild taxonomy artifact
- [ ] Routing verified: philosophy question → philosophy books

**Verification:**
```bash
# Ask "How should I think about security?" → get security books
# Ask "What did Aurelius say about death?" → get Meditations
```

---

### M4.4: Artifact Verification

**What "complete" means:**
- [ ] All books in DB are in book_index artifact
- [ ] All chapters in DB are in chapter_index artifact
- [ ] Taxonomy artifact maps all domains correctly
- [ ] Agents load artifacts on startup
- [ ] Hot-reload works (change artifact → agent uses new data)

**Verification:**
```bash
# Add new book via ingestion
# Rebuild artifacts
# Ask question in that domain → new book appears in routing
```

---

### Phase 4 Exit Criteria

- [ ] No duplicate books
- [ ] Key books have real chapters
- [ ] Domain assignments are accurate
- [ ] Artifacts are in sync with DB
- [ ] Routing is reliable

---

## Phase 5: Polish & Launch

**Goal**: Ready for real users.
**Duration**: Days 6-7
**Blocking**: User trust, stability.

### M5.1: Performance Check

**What "complete" means:**
- [ ] Homepage loads < 2s
- [ ] Library with 100+ books loads < 3s
- [ ] Reader loads < 2s
- [ ] Add indexes if queries are slow
- [ ] No N+1 queries (check logs)

---

### M5.2: Security Audit

**What "complete" means:**
- [ ] All user data operations check ownership
- [ ] SQL injection impossible (parameterized queries)
- [ ] XSS mitigated (Jinja2 auto-escape)
- [ ] CSRF protected for mutations (forms have tokens or same-origin check)
- [ ] Secrets not in code or logs
- [ ] Error pages don't leak internals

---

### M5.3: Full Smoke Test

**What "complete" means:**
- [ ] Run entire SMOKE_TESTS.md checklist
- [ ] Document any failures
- [ ] Fix launch blockers
- [ ] Accept known issues (document them)

---

### M5.4: Documentation

**What "complete" means:**
- [ ] README updated with production setup
- [ ] Admin workflow documented
- [ ] Known issues documented
- [ ] Quick start for developers

---

### Phase 5 Exit Criteria

- [ ] Smoke tests pass
- [ ] No launch blockers
- [ ] Documentation complete
- [ ] Ready to share URL

---

## Post-Launch (Phase 6+)

Only after real users are on the platform:

1. **Email notifications** - User knows when request approved/added
2. **In-text highlight rendering** - Highlights visible in text, not just rail
3. **Progress tracking** - Remember reading position
4. **Search within book** - Full-text search in reader
5. **Export highlights** - CSV/PDF of user's highlights
6. **Mobile optimization** - Touch-friendly reader
7. **PDF viewer/download** - Alternative to extracted text

---

## Progress Tracking

| Phase | Status | Completion |
|-------|--------|------------|
| Phase 1: Infrastructure | Not started | 0% |
| Phase 2: User Features | Not started | 0% |
| Phase 3: Admin Ops | Not started | 0% |
| Phase 4: Canon Quality | Not started | 0% |
| Phase 5: Polish | Not started | 0% |

**Last updated**: [Date]

---

## The Rule

Before marking anything complete:

1. Does it satisfy ALL 8 criteria? (Write/Read/Perms/Valid/Empty/Loading/Error/Test)
2. Can someone else verify it without asking questions?
3. Would you be embarrassed if a user hit this feature right now?

If yes to #3, it's not done.
