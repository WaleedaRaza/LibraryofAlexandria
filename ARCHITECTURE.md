# Alexandria - Complete Architecture & Completion Criteria

## What Alexandria Is

Alexandria is a **knowledge aggregation and guided reading platform**. It is:

1. **A Library** - Curated collection of texts (the Canon)
2. **A Router** - Agent-guided navigation from questions to relevant passages
3. **A Reader** - Focused reading experience with highlights and notes
4. **A Growth Engine** - User requests → Admin approval → Canon expansion

The platform operates with **discretion** - books are added through a controlled pipeline, not scraped or pirated. The legal model: users request, admins curate, the canon grows.

---

## The Three Pipelines

### Pipeline 1: USER JOURNEY
```
[Ask Question] → [Intent Classification] → [Reading Routing] → [Reader View]
                                                                    ↓
                                                            [Highlight Text]
                                                                    ↓
                                                            [Ask About Selection]
                                                                    ↓
                                                            [Text Companion Response]
```

### Pipeline 2: ADMIN CURATION
```
[View Requests] → [Approve/Reject] → [Acquire Book] → [Ingest PDF] → [Generate Artifacts]
                                                                            ↓
                                                                    [Canon Updated]
                                                                            ↓
                                                                    [User Notified]
```

### Pipeline 3: CANON LIFECYCLE
```
[PDF Source] → [Text Extraction] → [Domain Inference] → [Chapter Detection] → [DB Insert]
                                                                                    ↓
                                                                            [Artifact Build]
                                                                                    ↓
                                                                            [Agents Updated]
```

---

## Architectural Layers

### Layer 0: Infrastructure
**What it is**: The substrate everything runs on.

| Component | Current State | Complete State |
|-----------|--------------|----------------|
| Database | SQLite (dev) | Postgres (Supabase) with connection pooling |
| Hosting | Local only | Render/Fly.io with auto-scaling |
| Static Assets | Local serving | CDN-backed, cache headers, versioned |
| Secrets | `.env` file | Platform env vars, rotatable |
| Monitoring | None | Health endpoint, error tracking (Sentry), basic analytics |
| CI/CD | None | GitHub Actions → auto-deploy on merge to main |

**Completion Criteria**:
- [ ] App boots with `DATABASE_URL` pointing to Postgres
- [ ] App runs without `OPENAI_API_KEY` (mock mode)
- [ ] App fails gracefully with clear errors on misconfiguration
- [ ] Static assets load from CDN with proper cache headers
- [ ] Health endpoint returns 200 with DB connectivity check
- [ ] Deploys automatically on push to main

---

### Layer 1: Data (The Canon)

**What it is**: The immutable source of truth for all books and chapters.

#### Tables:
| Table | Purpose | Mutability |
|-------|---------|------------|
| `books` | Book metadata (title, author, domain) | Admin-only writes |
| `book_text` | Full text content (one row per book) | Admin-only writes |
| `chapters` | Chapter boundaries (offsets into book_text) | Admin-only writes |

#### Invariants:
1. **Canon is singular** - `book_text.content` is THE text. Chapters reference offsets, never duplicate.
2. **Books are unique** - No duplicate `(title, author)` pairs. Ingestion is idempotent.
3. **Chapters are contiguous** - `end_offset[n] == start_offset[n+1]` for sequential chapters.
4. **Domain is validated** - Only values from the taxonomy whitelist.

#### Completion Criteria:
- [ ] Ingestion is idempotent (rerun does not duplicate)
- [ ] Chapter detection produces meaningful splits (not just "Full Text")
- [ ] Domain inference is accurate (or defaults are sensible)
- [ ] Artifacts rebuild deterministically from DB
- [ ] Unique constraint on `(title, author)` enforced
- [ ] Admin can manually override domain/subdomain

---

### Layer 2: User Data (Mutable)

**What it is**: Everything specific to a user's experience.

#### Tables:
| Table | Purpose | Owner |
|-------|---------|-------|
| `users` | Account info, role (user/admin) | User owns their row |
| `sessions` | Auth tokens with expiry | System manages |
| `saved_books` | User's personal library | User |
| `highlights` | Text selections with offsets | User |
| `annotations` | Notes attached to highlights | User |
| `book_requests` | Wishlist items with status | User creates, Admin resolves |

#### Invariants:
1. **Ownership is enforced** - Users can only CRUD their own data.
2. **Highlights reference valid chapters** - FK constraint + application check.
3. **Annotations are 1:1 with highlights** - One note per highlight max.
4. **Sessions expire** - 7-day TTL, cleaned up on logout.
5. **Passwords are bcrypt** - Never SHA256 in production.

#### Completion Criteria:
- [ ] All user data operations check ownership
- [ ] Passwords use bcrypt with cost factor 12
- [ ] Session cookies are `HttpOnly`, `Secure`, `SameSite=Lax`
- [ ] Expired sessions are cleaned up (cron or on-access)
- [ ] Highlights persist and render on reload
- [ ] Annotations persist and render on reload
- [ ] Delete cascade works (delete highlight → delete annotation)

---

### Layer 3: Services

**What it is**: Business logic layer between routes and data.

| Service | Responsibility | State |
|---------|---------------|-------|
| `CanonService` | Read books, chapters, text | ✅ Complete |
| `UserService` | Highlights, saves, annotations | ⚠️ Works, but no ownership checks on annotation delete |
| `RequestService` | Book request lifecycle | ✅ Complete (needs UI) |
| `AgentService` | Orchestrates the three agents | ✅ Complete |

#### Completion Criteria:
- [ ] Each service has a single responsibility
- [ ] Services don't touch HTTP (no Request/Response objects)
- [ ] All mutations check permissions
- [ ] All reads are scoped appropriately (user sees their data, admin sees all)
- [ ] Error cases return typed results, not exceptions

---

### Layer 4: Agents

**What it is**: The AI brain that routes and explains.

| Agent | Input | Output | Constraints |
|-------|-------|--------|-------------|
| IntentClassifier | User question | Domain + subdomain + confidence | Never answers the question |
| ReadingRouter | Domain + available books | 2-4 parallel reading paths | Never summarizes, never recommends outside taxonomy |
| TextCompanion | Selected text + question | Explanation of the selection | Only explains selection, refuses advice/modern application |

#### Invariants:
1. **Agents are stateless** - No DB access, no side effects.
2. **Taxonomy gate is enforced** - Router cannot recommend books outside the gate.
3. **Refusals are graceful** - Bad input → clear message, not crash.
4. **Mock mode is complete** - Every agent works without LLM.
5. **Cache prevents waste** - Identical routing queries hit cache.

#### Completion Criteria:
- [ ] Each agent has mock mode that passes same contract tests as LLM mode
- [ ] Taxonomy gate blocks hallucinated book IDs
- [ ] Routing cache has TTL and max size
- [ ] TextCompanion refuses cross-book synthesis
- [ ] TextCompanion refuses "what should I do" questions
- [ ] Agent responses are logged for debugging (not user content, just agent name + success/fail)

---

### Layer 5: Routes (HTTP)

**What it is**: The API surface. Thin. Delegates to services.

| Router | Prefix | Endpoints | Auth Required |
|--------|--------|-----------|---------------|
| `pages` | `/` | Home, About | No |
| `ask` | `/ask` | POST question | No |
| `library` | `/library` | Browse, detail, save/unsave | Save requires auth |
| `reader` | `/read` | Read, highlight, annotate, chat | Highlight/annotate requires auth |
| `wishlist` | `/wishlist` | View requests, submit, cancel | All require auth |
| `auth` | `/auth` | Login, register, logout | N/A |
| `admin` | `/admin` | Request management, book ingestion | **Admin role required** |

#### Invariants:
1. **Routes are thin** - Max 20 lines per endpoint. Logic lives in services.
2. **Auth is consistent** - Use dependency injection, not inline checks.
3. **Errors are handled** - 404 for not found, 401 for unauth, 403 for forbidden.
4. **Rate limiting protects expensive endpoints** - Ask and Chat are rate-limited.

#### Completion Criteria:
- [ ] All routes have explicit auth requirements (none, user, admin)
- [ ] Rate limiting on `/ask` and `/read/*/chat`
- [ ] 404 page renders for invalid book/chapter IDs
- [ ] 403 page renders for admin routes accessed by non-admin
- [ ] CORS configured for production domain

---

### Layer 6: Templates & Frontend

**What it is**: The user-facing experience.

| Template | Purpose | Dynamic Elements |
|----------|---------|------------------|
| `index.html` | Homepage + ask prompt | Ask form |
| `routing_results.html` | Display parallel reading paths | Path cards with links |
| `library.html` | Browse books | Domain filter, search, grid |
| `book_detail.html` | Single book view | Chapter list, save button |
| `reader.html` | Reading experience | Text, sidebar, annotations, chat |
| `wishlist.html` | Book requests | Request list, status badges |
| `my_library.html` | Saved books | Book grid, unsave buttons |
| `auth/*.html` | Login/register | Forms, error messages |
| `errors/*.html` | 404, 500 | Friendly error pages |

#### Frontend JS:
| File | Purpose |
|------|---------|
| `reader.js` | Text selection, highlight creation, chat panel |

#### Invariants:
1. **Progressive enhancement** - Core reading works without JS.
2. **Feedback is immediate** - Actions show loading states, success confirms.
3. **Errors are friendly** - Never show stack traces to users.
4. **Mobile works** - Reader is usable on phone (even if not optimized).

#### Completion Criteria:
- [ ] Homepage shows clear value prop and ask prompt
- [ ] Routing results show paths as cards, not a list
- [ ] Reader shows context banner ("You were directed here because...")
- [ ] Highlight appears visually when created
- [ ] Highlights load and display on page refresh
- [ ] Annotations display in rail
- [ ] Chat panel shows selected text and response
- [ ] Empty states for all lists (no books, no highlights, no requests)
- [ ] Loading states for async operations
- [ ] Success confirmations for mutations

---

### Layer 7: Admin Operations

**What it is**: The curator's toolset.

#### Admin UI:
| Page | Purpose |
|------|---------|
| `/admin/requests` | View all book requests, filter by status |
| `/admin/requests/{id}` | Request detail, approve/reject actions |
| `/admin/books` | View all books, edit metadata (future) |
| `/admin/ingest` | Upload PDF for ingestion (future) |

#### Admin CLI:
| Command | Purpose |
|---------|---------|
| `python -m admin.ingest_books --pdf` | Ingest single PDF |
| `python -m admin.ingest_books --dir` | Batch ingest directory |
| `python -m admin.build_artifacts` | Rebuild JSON artifacts |

#### Invariants:
1. **Admin routes are guarded** - Non-admin gets 403, not 404.
2. **Actions are auditable** - Timestamps on all state changes.
3. **Ingestion is idempotent** - Rerun doesn't break things.
4. **Artifacts are deterministic** - Same DB → same artifacts.

#### Completion Criteria:
- [ ] Admin can view pending requests in web UI
- [ ] Admin can approve with optional note
- [ ] Admin can reject with required note
- [ ] Admin can mark request as ADDED
- [ ] User sees status update on their wishlist
- [ ] CLI ingestion outputs clear success/failure per book
- [ ] Artifact build logs what changed

---

## Feature Completion Matrix

For each feature, "complete" means ALL of these:

| Criterion | Meaning |
|-----------|---------|
| **Write path** | User can create/update the thing |
| **Read path** | User can view the thing after reload |
| **Permissions** | Only authorized users can act |
| **Validation** | Bad input → helpful error, not crash |
| **Empty state** | Clear UI when no data exists |
| **Loading state** | Feedback during async operations |
| **Error state** | Graceful handling of failures |
| **Smoke test** | Manual verification script exists |

### User Features:

| Feature | Write | Read | Perms | Valid | Empty | Loading | Error | Test |
|---------|-------|------|-------|-------|-------|---------|-------|------|
| Register | ✅ | ✅ | N/A | ⚠️ | N/A | ❌ | ✅ | ❌ |
| Login | ✅ | ✅ | N/A | ⚠️ | N/A | ❌ | ✅ | ❌ |
| Ask | ✅ | ✅ | N/A | ⚠️ | ✅ | ❌ | ⚠️ | ❌ |
| Browse Library | N/A | ✅ | N/A | N/A | ✅ | ❌ | ⚠️ | ❌ |
| Read | N/A | ✅ | N/A | ⚠️ | N/A | ❌ | ⚠️ | ❌ |
| Highlight | ✅ | ❌ | ⚠️ | ⚠️ | ✅ | ❌ | ⚠️ | ❌ |
| Annotate | ✅ | ❌ | ⚠️ | ⚠️ | ✅ | ❌ | ⚠️ | ❌ |
| Chat | ✅ | ✅ | N/A | ⚠️ | N/A | ⚠️ | ⚠️ | ❌ |
| Save Book | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ⚠️ | ❌ |
| Request Book | ✅ | ✅ | ✅ | ⚠️ | ✅ | ❌ | ⚠️ | ❌ |

Legend: ✅ Complete | ⚠️ Partial/Untested | ❌ Missing

### Admin Features:

| Feature | Write | Read | Perms | Valid | Empty | Loading | Error | Test |
|---------|-------|------|-------|-------|-------|---------|-------|------|
| View Requests | N/A | ❌ | ❌ | N/A | ❌ | ❌ | ❌ | ❌ |
| Approve/Reject | ❌ | ❌ | ❌ | ❌ | N/A | ❌ | ❌ | ❌ |
| Ingest Book | ✅ | N/A | N/A | ⚠️ | N/A | N/A | ⚠️ | ⚠️ |
| Build Artifacts | ✅ | N/A | N/A | ⚠️ | N/A | N/A | ⚠️ | ⚠️ |

---

## Deployment Architecture

### Current (Dev):
```
[Browser] → [localhost:5050] → [SQLite file]
```

### Target (Production):
```
                                   ┌──────────────────┐
                                   │   Supabase       │
                                   │   (Postgres)     │
                                   └────────▲─────────┘
                                            │
┌──────────┐     ┌─────────────────┐    ┌───┴───────────┐
│  Browser │────▶│  Render/Fly.io  │───▶│  FastAPI App  │
└──────────┘     │  (Container)    │    │  (Uvicorn)    │
                 └─────────────────┘    └───────────────┘
                         │
                         ▼
                 ┌─────────────────┐
                 │  Static Assets  │
                 │  (CDN optional) │
                 └─────────────────┘
```

### Why Render/Fly.io (not Vercel):
- Vercel is serverless → ephemeral filesystem → no SQLite
- Vercel cold starts → slow first request
- Render/Fly.io = persistent container → real process, real filesystem

### Environment Variables (Production):
```bash
# Required
DATABASE_URL=postgresql://user:pass@host:5432/alexandria
SESSION_SECRET=<random 64-char hex>
ENV=production

# Optional
OPENAI_API_KEY=sk-...  # If missing, mock mode
USE_MOCK_AGENTS=false  # Set true to force mock even with key
DEBUG=false
```

---

## The Path to Production

### Phase 1: Infrastructure Foundation (Days 1-2)
Goal: App runs on real infrastructure with real persistence.

1. **Provision Supabase project**
   - Create project
   - Get connection string
   - Run schema.sql to create tables

2. **Update database layer**
   - Add Postgres connection handling
   - Handle `DATABASE_URL` format
   - Ensure SQL compatibility

3. **Security baseline**
   - bcrypt for passwords
   - Secure cookies when `ENV=production`
   - Admin role check

4. **Env validation**
   - Validate required vars on startup
   - Force mock mode if OPENAI_API_KEY missing
   - Clear error messages

5. **Deploy to Render**
   - Create web service
   - Configure env vars
   - Verify health endpoint

**Exit Criteria**: App accessible at public URL, register/login works, library browses.

---

### Phase 2: User Feature Completion (Days 3-4)
Goal: Every user feature works end-to-end with proper feedback.

1. **Highlight persistence**
   - Load highlights on GET /read/{id}
   - Render in annotations rail
   - Show snippet + timestamp

2. **Annotation persistence**
   - Load with highlights
   - Display in rail
   - Edit/delete works

3. **Chat polish**
   - Loading state during LLM call
   - Error state on failure
   - Constraint message clear

4. **Empty/error states**
   - No books found → clear message
   - No highlights → invite to highlight
   - Rate limit hit → friendly message

5. **Ask flow polish**
   - Loading state during routing
   - Context banner in reader
   - Graceful handling of no routes

**Exit Criteria**: User can complete full loop (ask → read → highlight → annotate → chat) with proper feedback at every step.

---

### Phase 3: Admin Operations (Days 4-5)
Goal: Admin can manage the platform without CLI.

1. **Admin routes**
   - `/admin/requests` - list with filters
   - `/admin/requests/{id}` - detail view
   - Guard with admin role check

2. **Request actions**
   - Approve with optional note
   - Reject with required note
   - Mark as ADDED

3. **Admin templates**
   - Request list page
   - Request detail page
   - Status badges

4. **Notifications (minimal)**
   - User sees status change on wishlist page
   - (Email is Phase 4)

**Exit Criteria**: Admin can manage request lifecycle entirely in browser.

---

### Phase 4: Canon Quality (Days 5-6)
Goal: The library is clean and properly categorized.

1. **Dedup existing books**
   - Identify duplicates by title similarity
   - Keep best version (most text, best metadata)
   - Remove duplicates

2. **Chapter detection**
   - Improve heuristics for chapter splitting
   - Or manual chapter definition for key books

3. **Domain refinement**
   - Review domain assignments
   - Add subdomain where appropriate
   - Rebuild taxonomy artifact

4. **Artifact verification**
   - Ensure all books in artifacts
   - Ensure all chapters indexed
   - Agents route correctly

**Exit Criteria**: Library has ~80 unique, well-categorized books with meaningful chapter splits.

---

### Phase 5: Polish & Launch (Days 6-7)
Goal: Ready for real users.

1. **Performance**
   - Add indexes if needed
   - Check page load times
   - Optimize queries if slow

2. **Security audit**
   - Test permission boundaries
   - Check for SQL injection (should be safe with parameterized queries)
   - Check XSS (Jinja2 auto-escapes)

3. **Smoke test suite**
   - Run full SMOKE_TESTS.md checklist
   - Document any known issues
   - Create "launch blockers" list

4. **Documentation**
   - Update README with production setup
   - Document admin workflows
   - Quick start for new developers

**Exit Criteria**: Smoke tests pass, no launch blockers, documentation complete.

---

## Success Metrics (Post-Launch)

How do we know it's working?

| Metric | Target |
|--------|--------|
| Uptime | 99%+ |
| Homepage to Reader conversion | >30% |
| Highlights per reading session | >2 |
| Book requests submitted | Growing week over week |
| Request → Added conversion | >50% of approved |

---

## The Golden Path

At every decision point, ask:

1. **Does this preserve canon integrity?** (No duplicates, no orphaned chapters)
2. **Does this respect ownership?** (Users own their data, admin curates canon)
3. **Does this fail gracefully?** (Clear errors, not crashes)
4. **Does this complete the loop?** (Write → Read → Persist → Display)
5. **Does this scale?** (Will it work with 10k books? 100k users?)

If the answer to any is "no" or "I don't know," stop and clarify before coding.

---

## Appendix: File Inventory

### Core Application (`app/`)
```
app/
├── __init__.py
├── config.py           # Settings from env vars
├── main.py             # FastAPI app, middleware, routes
├── agents/
│   ├── contracts.py    # Data structures (IntentResult, etc.)
│   ├── domain_mapper.py
│   ├── intent_classifier.py
│   ├── llm_provider.py
│   ├── reading_router.py
│   ├── routing_cache.py
│   ├── taxonomy.py     # V1 hardcoded
│   ├── taxonomy_v2.py  # V2 artifact-based
│   └── text_companion.py
├── db/
│   ├── database.py     # Connection management
│   └── schema.sql      # Table definitions
├── middleware/
│   └── rate_limit.py   # Request throttling
├── routes/
│   ├── ask.py          # POST /ask
│   ├── auth.py         # Login/register/logout
│   ├── library.py      # Browse, save, unsave
│   ├── pages.py        # Home, about
│   ├── reader.py       # Read, highlight, chat
│   └── wishlist.py     # Book requests
└── services/
    ├── agent_service.py
    ├── canon_service.py
    ├── request_service.py
    └── user_service.py
```

### Admin Tools (`admin/`)
```
admin/
├── __init__.py
├── build_artifacts.py  # Generate JSON indexes
└── ingest_books.py     # PDF → DB ingestion
```

### Templates (`templates/`)
```
templates/
├── base.html
├── index.html
├── about.html
├── routing_results.html
├── library.html
├── book_detail.html
├── reader.html
├── my_library.html
├── wishlist.html
├── auth/
│   ├── login.html
│   └── register.html
├── errors/
│   ├── 404.html
│   └── 500.html
└── partials/
    └── chat_response.html
```

### Static Assets (`static/`)
```
static/
├── css/
│   ├── main.css
│   └── reader.css
└── js/
    └── reader.js
```

### Artifacts (`artifacts/`)
```
artifacts/
├── book_index.v1.json    # All books with metadata
├── chapter_index.v1.json # All chapters
└── taxonomy.v1.json      # Domain → book mappings
```

---

*This document is the architectural source of truth. Update it when architecture changes.*
