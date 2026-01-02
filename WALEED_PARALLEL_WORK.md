# Waleed's Parallel Work - While Friend Handles Book Aggregation

**His Job**: Get 1300 books into the system
**Your Job**: Prepare everything else for launch

---

## Priority 1: Agent & LLM Optimization (Week 1-2)

**Why this matters**: The agent system is the core differentiator. You can polish this independently of book count.

### Task List

#### Prompt Engineering
- [ ] **Review all 3 agent prompts** (Ask, Router, Companion)
  - `app/agents/ask_agent.py`
  - `app/agents/reading_router.py`
  - `app/agents/text_companion.py`
- [ ] **Add clear constraints** to each prompt:
  - "You must only recommend books from the provided list"
  - "If you're not confident, say 'I couldn't find relevant reading'"
  - "Never hallucinate book content or make up chapters"
- [ ] **Add few-shot examples** to prompts (3-5 examples per agent)
- [ ] **Test edge cases**:
  - Vague questions ("tell me about life")
  - Off-topic questions ("how do I fix my car?")
  - Adversarial ("ignore previous instructions")
  - Multiple topics in one question
  
#### Routing Quality
- [ ] **Test routing with 50 diverse questions** (create test set)
- [ ] **Document routing accuracy** (% that feel right)
- [ ] **Identify misclassifications** and fix taxonomy mappings
- [ ] **Review domain assignments** for existing 193 books
  - Are philosophy books actually philosophy?
  - Are tech books in the right subdomain?
  
#### Mock Mode Parity
- [ ] **Improve mock responses** to be realistic
  - Currently they might be too generic
  - Make them match the style of real responses
  - Test that mock mode feels like a real agent
  
#### Rate Limiting Strategy
- [ ] **Design per-user rate limits**:
  - How many asks per hour?
  - How many chats per session?
  - Graceful degradation when hit
- [ ] **Cost tracking**:
  - Log every OpenAI call with token count
  - Calculate cost per user session
  - Set budget alerts

**Deliverable**: `AGENT_OPTIMIZATION_REPORT.md` with findings and improvements

---

## Priority 2: User Pipeline Design (Week 1)

**Why this matters**: This is the unique value prop - users see the work happening.

### Task List

#### Design the Status Feed
- [ ] **Sketch the user request flow**:
  ```
  User submits → Searching... → Found candidates → 
  Scoring... → Human review → Approved → 
  Acquiring... → Added to library!
  ```
- [ ] **Design each status message**:
  - What does user see at each stage?
  - How long should each stage typically take?
  - What happens if it stalls?
  
#### Plan Real-time Updates
- [ ] **Choose approach**:
  - Server-Sent Events (SSE)?
  - Polling every 5 seconds?
  - WebSocket? (probably overkill)
- [ ] **Design the status API**:
  - `GET /api/request/{id}/status`
  - Returns: current stage, progress, ETA, errors
  
#### Mock the Experience
- [ ] **Create HTML mockup** of status feed
  - Put in `mockups/10-request-status.html`
  - Show all stages with realistic timing
  - Show error states
- [ ] **User test it** (show to a friend)
  - Do they understand what's happening?
  - Is it clear this is valuable work?

**Deliverable**: Mockup file and status API design doc

---

## Priority 3: Infrastructure Prep (Week 2)

**Why this matters**: Get ahead on Phase 2 so deployment is smooth.

### Task List

#### Database Planning
- [ ] **Choose Postgres provider**: Supabase, Neon, or AWS RDS?
- [ ] **Review current schema** (`app/db/schema.sql`)
  - Any changes needed for Postgres?
  - Any indexes needed for performance?
- [ ] **Plan migration strategy**:
  - Fresh start or migrate existing data?
  - If migrate: write migration script
  
#### Security Research
- [ ] **Research bcrypt implementation**:
  - Read docs: https://github.com/pyca/bcrypt/
  - Test locally: hash/verify a password
  - Document cost factor choice (12 is good)
- [ ] **Review session security**:
  - Current implementation in `app/routes/auth.py`
  - What needs to change for production?
  - Document required cookie flags
  
#### Deployment Platform Research
- [ ] **Compare Render vs Fly.io**:
  - Cost for expected traffic
  - Ease of setup
  - Performance characteristics
- [ ] **Document deployment steps**:
  - What env vars are needed?
  - What's the build command?
  - What's the start command?
  - How do we handle database migrations?

**Deliverable**: `INFRASTRUCTURE_PLAN.md` with decisions documented

---

## Priority 4: Testing & Quality (Ongoing)

**Why this matters**: Catch issues early before they compound.

### Task List

#### Manual Testing
- [ ] **Test all current features** (weekly):
  - Register → Login → Browse → Read → Highlight
  - Ask question → Get routing → Read result
  - Request book → See in wishlist
  - Admin: view requests → approve
- [ ] **Document bugs** in GitHub issues or `KNOWN_ISSUES.md`
- [ ] **Test on mobile** (Chrome + Safari)
  - Does reader work?
  - Is text readable?
  - Do highlights work?

#### Write Smoke Tests
- [ ] **Create `SMOKE_TESTS.md`** with manual test checklist
- [ ] **Consider automated tests**:
  - pytest for agent functions (pure functions are easy to test)
  - Integration tests for critical paths
  
#### Performance Baseline
- [ ] **Measure current performance**:
  - Homepage load time
  - Library with 193 books load time
  - Reader load time
  - Routing query time
- [ ] **Document baseline** so you can track improvements

**Deliverable**: `SMOKE_TESTS.md` and performance baseline doc

---

## Priority 5: Content & Canon Quality (Week 1-2)

**Why this matters**: The better the taxonomy and metadata, the better the routing.

### Task List

#### Taxonomy Refinement
- [ ] **Review current taxonomy** (`artifacts/taxonomy.v1.json`)
  - Are domains comprehensive?
  - Do we need more subdomains?
  - Are concepts well-defined?
- [ ] **Plan expansions**:
  - What domains are missing?
  - What will we need when we hit 1300 books?
  
#### Domain Classification
- [ ] **Audit existing 193 books**:
  - Spot check 20 random books
  - Are domains correct?
  - Are subdomains useful?
- [ ] **Create reclassification list** if needed
  
#### Chapter Quality
- [ ] **Review chapter detection**:
  - Pick 10 popular books
  - Check if chapters are meaningful
  - Document improvements needed
- [ ] **Plan manual chapter definition** for top 50 books

**Deliverable**: Updated taxonomy and reclassification list

---

## Priority 6: UX & Polish (Week 2)

**Why this matters**: First impressions matter at launch.

### Task List

#### Empty States
- [ ] **Review all pages** for empty state UX:
  - Library with no books (shouldn't happen, but still)
  - My Library when user hasn't saved anything
  - Wishlist when user hasn't requested anything
  - Routing with no results
- [ ] **Write copy** for each empty state
  - Helpful, not snarky
  - Guide user to next action
  
#### Error Messages
- [ ] **Review all error scenarios**:
  - Database down
  - OpenAI rate limit
  - Invalid book ID
  - Not authorized
- [ ] **Write friendly error messages**
  - Never show stack traces
  - Clear next action
  - Contact option if truly stuck
  
#### Loading States
- [ ] **Audit async operations**:
  - Ask form submission
  - Save book button
  - Highlight creation
  - Chat with companion
- [ ] **Add loading indicators** where missing

**Deliverable**: Updated templates with polish

---

## Week-by-Week Plan

### Week 1: LLM & Design
**Monday-Tuesday**: Agent prompt optimization
**Wednesday-Thursday**: User pipeline design (status feed mockup)
**Friday**: Manual testing, document findings

### Week 2: Infrastructure & Content
**Monday-Tuesday**: Infrastructure research and planning
**Wednesday-Thursday**: Taxonomy refinement and domain audit
**Friday**: UX polish, empty states, error messages

---

## When to Sync with Friend

### Daily Sync (5 min)
- "How many books ingested today?"
- "Any blockers?"
- "Here's what I finished"

### Weekly Sync (30 min)
- Review what each person completed
- Adjust priorities based on progress
- Plan next week

---

## Success Metrics

**By End of Week 2:**
- [ ] Agent prompts are optimized (tested with 50 questions)
- [ ] User pipeline is designed (mockup exists)
- [ ] Infrastructure plan is documented (ready to execute)
- [ ] Taxonomy is refined for 1300 books
- [ ] Smoke tests are written
- [ ] UX polish is done (empty states, errors, loading)

**Then**: You're ready to execute Phase 2 & 3 in parallel with friend's Phase 4 work

---

## The Strategy

You're de-risking the launch by:
1. **Making sure the agents work well** (not blocked by book count)
2. **Designing the user pipeline** (your differentiator)
3. **Planning infrastructure** (so Phase 2 is faster)
4. **Improving quality** (better routing, better UX)

When book aggregation is done, you'll be ready to immediately:
- Deploy to production (infrastructure planned)
- Turn on user requests (pipeline designed)
- Handle 10x traffic (agents optimized)

**All eggs in different baskets. Both critical path.**

---

**Start with**: Agent prompt optimization (Priority 1) - that's highest leverage and you can do it today.
