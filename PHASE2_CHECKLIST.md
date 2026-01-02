# Phase 2: Infrastructure & Auth - Daily Checklist

**Goal**: Production-ready foundation in 2 weeks
**Your Role**: Execute this, Waleed is handling book aggregation

---

## Week 1: Database & Security

### Day 1: Postgres Setup
- [ ] Create Supabase project
- [ ] Get `DATABASE_URL` connection string
- [ ] Apply schema from `app/db/schema.sql` to Postgres
- [ ] Test connection from local machine
- [ ] Document credentials in secure location

### Day 2: Database Migration
- [ ] Update `app/db/database.py` for Postgres connections
- [ ] Replace SQLite-specific syntax (if any)
- [ ] Test connection pooling works
- [ ] Verify app boots with Postgres
- [ ] Run smoke test: register user, browse library, read book

### Day 3: Security - Passwords
- [ ] Add `bcrypt` to `requirements.txt` (latest version)
- [ ] Implement `hash_password()` using bcrypt cost factor 12
- [ ] Implement `verify_password()` using bcrypt verify
- [ ] Test: Register new user → check DB password starts with `$2b$`
- [ ] Test: Login with correct password → success
- [ ] Test: Login with wrong password → fails
- [ ] Document: Migration path for existing users (if any)

### Day 4: Security - Sessions
- [ ] Update session cookie creation with flags:
  - `httponly=True`
  - `secure=True` (when `ENV=production`)
  - `samesite="lax"`
- [ ] Test in browser dev tools → verify flags set
- [ ] Implement session expiry (7 days TTL)
- [ ] Test: Login → Close browser → Reopen → Still logged in
- [ ] Test: Wait 7 days (or manually expire) → Logged out

### Day 5: Security - Admin Guards
- [ ] Verify `role` field exists in users table
- [ ] Create `require_admin` dependency in `app/routes/auth.py`
- [ ] Apply `require_admin` to all `/admin/*` routes:
  - `admin.py` - requests list, detail, approve, reject, mark added
- [ ] Create at least one admin user (manually update DB `role='admin'`)
- [ ] Test: Login as regular user → Try `/admin/requests` → Get 403
- [ ] Test: Login as admin → Access `/admin/requests` → Success

---

## Week 2: Deployment & Hardening

### Day 6: Environment Validation
- [ ] Add startup checks in `app/main.py`:
  - Check `DATABASE_URL` → Fail with clear message if missing
  - Check `SESSION_SECRET` → Fail if missing (use `SECRET_KEY` for now)
  - If `OPENAI_API_KEY` missing → Force `USE_MOCK_AGENTS=true`, log warning
- [ ] Create `/health` endpoint:
  - Returns `{"status": "ok", "db": "connected"}` when healthy
  - Returns `{"status": "error", "db": "disconnected"}` with 500 when DB down
- [ ] Test: Start with no `DATABASE_URL` → See clear error
- [ ] Test: Start with no `OPENAI_API_KEY` → App runs in mock mode
- [ ] Test: Hit `/health` → Get 200 with JSON

### Day 7: Deployment Prep
- [ ] Choose platform: Render or Fly.io (recommend Render for simplicity)
- [ ] Create `render.yaml` or configure manual service
- [ ] Set build command: `pip install -r requirements.txt`
- [ ] Set start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- [ ] Document environment variables needed:
  - `DATABASE_URL`
  - `SESSION_SECRET`
  - `ENV=production`
  - `OPENAI_API_KEY` (optional)

### Day 8: Deploy to Production
- [ ] Push code to main branch
- [ ] Configure environment variables in Render/Fly.io
- [ ] Trigger first deployment
- [ ] Check logs for errors
- [ ] Visit production URL → Homepage loads
- [ ] Test: Register account
- [ ] Test: Login works
- [ ] Test: Browse library

### Day 9: Production Verification
- [ ] Verify static files load (CSS, fonts)
- [ ] Verify health check: `https://your-app.com/health` → 200
- [ ] Test all major flows on production:
  - Register → Login → Browse → Read → Highlight
  - Admin login → View requests → Approve/reject
- [ ] Check that passwords in production DB start with `$2b$`
- [ ] Verify session cookies have `Secure` flag in production

### Day 10: Error Tracking & Polish
- [ ] Set up error tracking (Sentry or similar)
- [ ] Test error scenarios:
  - Invalid book ID → 404 page
  - Database down → 500 page (friendly, no stack trace)
  - Rate limit exceeded → Clear message
- [ ] Add friendly error pages if not already done
- [ ] Document any known issues
- [ ] Write deployment runbook for future reference

---

## Exit Criteria (Must All Be True)

### Security
- [ ] Passwords are bcrypt with cost 12
- [ ] Session cookies are `HttpOnly`, `Secure` (in prod), `SameSite=Lax`
- [ ] Admin routes return 403 for non-admin users
- [ ] All sensitive operations check permissions

### Deployment
- [ ] Production URL is accessible
- [ ] Users can register and login
- [ ] Library browsing works
- [ ] Reader works
- [ ] Health endpoint returns 200
- [ ] App runs without `OPENAI_API_KEY` (mock mode)

### Database
- [ ] App uses Postgres (not SQLite)
- [ ] All queries work on Postgres
- [ ] Connection pooling works
- [ ] Data persists across deployments

### Polish
- [ ] No stack traces shown to users
- [ ] 404/500 pages are friendly
- [ ] Logs are clean (no secrets, minimal noise)
- [ ] README updated with production setup

---

## Daily Standup Questions

1. **What did I complete yesterday?**
2. **What am I working on today?**
3. **Am I blocked on anything?**
4. **Do I need Waleed's input on any decisions?**

---

## Common Gotchas

### Database
- **Gotcha**: SQLite uses `AUTOINCREMENT`, Postgres uses `SERIAL`
- **Fix**: Check schema, update if needed

### Passwords
- **Gotcha**: Bcrypt is slow (intentionally)
- **Fix**: This is normal, 12 rounds is secure

### Deployment
- **Gotcha**: Static files don't load
- **Fix**: Check `STATIC_URL` and static files serving config

### Sessions
- **Gotcha**: Sessions don't persist after deployment restart
- **Fix**: Use DB-backed sessions or ensure cookies are set correctly

---

## Resources

- [Supabase Docs](https://supabase.com/docs)
- [FastAPI Postgres](https://fastapi.tiangolo.com/tutorial/sql-databases/)
- [Bcrypt Python](https://github.com/pyca/bcrypt/)
- [Render Docs](https://render.com/docs)
- [Fly.io Docs](https://fly.io/docs/)

---

## When You're Done

1. Update `ROADMAP.md` with Phase 2 completion
2. Run full smoke test (use `SMOKE_TESTS.md` if it exists)
3. Document any issues or workarounds
4. Sync with Waleed: "Phase 2 complete, moving to Phase 3"

**Then move to Phase 3: LLM & Agent Hardening**

---

**Last Updated**: January 1, 2026
