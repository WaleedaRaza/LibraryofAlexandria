# Alexandria Smoke Tests

## Purpose

This is your "production launch checklist." Run these tests before declaring any milestone complete, and especially before inviting real users.

---

## Pre-Deployment Smoke Tests

Run these against your staging/local environment before deploying.

### Authentication & Sessions

- [ ] Register new account with email + password
- [ ] Login with correct credentials → redirects to home
- [ ] Login with incorrect credentials → error message shown
- [ ] Logout → session cleared, redirected
- [ ] Login again → session persists across page refresh
- [ ] Close browser, reopen → still logged in (within 7 days)
- [ ] Access protected route while logged out → redirects to login

### Library Browsing

- [ ] Load `/library` → books display in grid
- [ ] Filter by domain (Philosophy, Strategy, etc.) → results update
- [ ] Search by title → relevant books appear
- [ ] Search by author → relevant books appear
- [ ] Click book card → opens book detail page
- [ ] Book detail shows: title, author, domain, chapter list
- [ ] Click "Start Reading" → opens reader on chapter 1

### Reader Experience

- [ ] Open `/read/{book_id}?chapter=1` → text loads
- [ ] Reader shows chapter navigation sidebar
- [ ] Click chapter in sidebar → loads that chapter
- [ ] Click "Next" → navigates to next chapter
- [ ] Click "Previous" → navigates to previous chapter
- [ ] Scroll page → text is readable (typography correct)
- [ ] Select text → popup menu appears (🖍️ 📝 💬)
- [ ] Popup menu positioned correctly (not off-screen)

### Highlights

- [ ] Select text → click 🖍️ → highlight created
- [ ] Console shows: `[Reader] Highlight created`
- [ ] Refresh page → highlight still visible in annotations rail
- [ ] Highlight shows: quoted text snippet, timestamp, color
- [ ] Click highlight in rail → (future: scrolls to position)
- [ ] Create multiple highlights → all persist on reload
- [ ] Delete highlight → removed from DB and UI

### Annotations

- [ ] Create highlight → click to add note
- [ ] Note saves and displays in annotations rail
- [ ] Refresh page → note still visible
- [ ] Edit note → changes persist
- [ ] Delete note → removed from UI and DB
- [ ] Delete highlight → associated note also deleted (or policy clear)

### Text Chat

- [ ] Select text → click 💬 → chat panel opens
- [ ] Selected text displays in chat panel
- [ ] Type question → click "Ask" → response appears
- [ ] Response is constrained (no advice, no modern applications)
- [ ] Ask off-topic question → agent refuses politely
- [ ] Close chat panel → annotations rail reappears
- [ ] Keyboard: Select text → press `C` → chat opens
- [ ] Keyboard: Press `Esc` → chat closes

### My Library

- [ ] Browse library → click "Save" on a book
- [ ] Navigate to `/library/my` → saved book appears
- [ ] Click saved book → opens book detail
- [ ] Click "Unsave" → book removed from My Library
- [ ] My Library empty state shows when no books saved

### Ask → Route → Read Flow

- [ ] Home page → type question in ask prompt
- [ ] Submit → routing results page loads
- [ ] Results show 2-4 reading paths with different angles
- [ ] Each path has book title, author, chapter, rationale
- [ ] Click chapter link → opens reader at that chapter
- [ ] Reader shows "You were directed here because..." context
- [ ] Ask nonsense question → empty state or graceful refusal

### Wishlist / Book Requests

- [ ] Navigate to `/wishlist`
- [ ] Click "Request a book" or similar
- [ ] Fill: title, author, reason
- [ ] Submit → request appears with PENDING status
- [ ] Cancel pending request → status updates or removed
- [ ] Admin approves request → status updates to APPROVED
- [ ] Admin marks as ADDED → status updates to ADDED

### Admin (if implemented)

- [ ] Login as admin user
- [ ] Access `/admin/requests` → list of requests loads
- [ ] Filter by status → results update
- [ ] Click request → detail view opens
- [ ] Approve request with note → status + timestamp update
- [ ] Reject request with note → status updates
- [ ] Mark as ADDED → status updates
- [ ] Login as normal user → attempt `/admin/requests` → 403 Forbidden

---

## Production Deployment Smoke Test

Run these tests **after deploying** to production URL.

### Critical Path (Must Pass)

1. **Homepage loads**
   - [ ] Visit production URL → page renders
   - [ ] CSS loads (text is styled, not Times New Roman)
   - [ ] No console errors

2. **Authentication works**
   - [ ] Register account → success
   - [ ] Login → redirects to home
   - [ ] Logout → session cleared

3. **Library browsing**
   - [ ] `/library` loads with books
   - [ ] Filter by domain works
   - [ ] Book detail page loads

4. **Reader works**
   - [ ] Open book → chapter text displays
   - [ ] CSS loaded (`reader.css`)
   - [ ] JS loaded (`reader.js`)
   - [ ] Select text → popup appears

5. **Highlights persist**
   - [ ] Create highlight → saves
   - [ ] Refresh page → highlight visible
   - [ ] Check database → highlight record exists

6. **Chat works**
   - [ ] Select text → open chat
   - [ ] Ask question → get response (mock or LLM)
   - [ ] Response displays correctly

7. **Save book**
   - [ ] Save book → appears in My Library
   - [ ] Unsave → removed

8. **Book request**
   - [ ] Submit wishlist request → PENDING status
   - [ ] Admin approves → status updates

9. **Ask flow**
   - [ ] Ask question → routing works
   - [ ] Click chapter → reader opens
   - [ ] Context banner shows

10. **Mobile check** (if time)
    - [ ] Load on phone → readable
    - [ ] Reader text is appropriately sized
    - [ ] Highlight menu shows on touch devices

---

## Performance Benchmarks (Production)

- [ ] Homepage loads in < 2s
- [ ] Library page with 100+ books loads in < 3s
- [ ] Reader page loads in < 2s
- [ ] Ask routing completes in < 5s (LLM) or < 1s (mock)
- [ ] Chat response in < 8s (LLM) or < 1s (mock)

---

## Failure Mode Tests

Test that errors are handled gracefully:

- [ ] Invalid book ID → 404 page
- [ ] Invalid chapter → 404 page
- [ ] Network timeout on LLM → error message (not crash)
- [ ] Database connection lost → 500 page (not white screen)
- [ ] Login with invalid session cookie → redirects to login
- [ ] Rate limit exceeded → 429 error message

---

## Environment Configuration Tests

- [ ] App boots with `DATABASE_URL` set
- [ ] App boots with `SESSION_SECRET` set
- [ ] App boots **without** `OPENAI_API_KEY` → mock mode works
- [ ] App boots with `OPENAI_API_KEY` → LLM mode works
- [ ] Invalid database URL → clear error message on startup
- [ ] Missing required env vars → fails with helpful message

---

## Security Checklist

- [ ] Passwords are bcrypt hashed (not SHA256)
- [ ] Sessions use `HttpOnly` cookies
- [ ] Sessions use `Secure` flag in production
- [ ] Sessions use `SameSite=Lax`
- [ ] Admin routes return 403 for non-admin users
- [ ] Users can only delete their own highlights/annotations
- [ ] SQL injection attempts are handled (parameterized queries)
- [ ] XSS attempts are escaped in templates

---

## Post-Launch Monitoring

After deployment, check:

- [ ] No errors in application logs (first 24h)
- [ ] Database connections stable
- [ ] Static files served correctly (check Network tab)
- [ ] SSL certificate valid
- [ ] Domain DNS resolves
- [ ] Health endpoint returns 200

---

## Sign-Off

**Date:** _______________

**Environment:** [ ] Local  [ ] Staging  [ ] Production

**Tested by:** _______________

**Result:** [ ] PASS - Ready to launch  [ ] FAIL - Blockers identified

**Blockers (if any):**

1. 
2. 
3. 

**Next steps:**

---

## Notes

- Run these tests **in order** - each section builds on the previous
- If any critical path test fails, **stop and fix** before proceeding
- Document any workarounds or known issues
- Update this file as you add new features
