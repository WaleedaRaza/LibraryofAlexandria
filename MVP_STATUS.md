# Alexandria MVP Status — Final Checkpoint

**Date:** January 2, 2026  
**Status:** Core functionality complete, ready for polish and launch prep

---

## ✅ WHAT'S WORKING

### 1. Authentication (Supabase Auth)
- [x] Email/password registration
- [x] Email confirmation flow with resend button (20s countdown)
- [x] Login/logout
- [x] Session cookies (`sb-access-token`, `sb-refresh-token`)
- [x] User dropdown menu with avatar when logged in
- [x] `get_current_user_optional` / `get_current_user_required` dependencies

**Routes:**
- `GET /auth/login` — Login page
- `POST /auth/login` — Process login
- `GET /auth/register` — Registration page
- `POST /auth/register` — Process registration
- `POST /auth/logout` — Logout
- `POST /auth/resend` — Resend confirmation email
- `GET /auth/confirm` — Email confirmation callback

### 2. Query → Domain → Books Pipeline
- [x] Intent Classifier maps queries to 1-3 domains (real LLM)
- [x] Reading Router selects books + chapters with rationales (real LLM)
- [x] Taxonomy synced with actual DB book IDs
- [x] Mock book fallback for domains without real books
- [x] Routing context passed to reader ("You were directed here because...")

**Routes:**
- `POST /ask/` — Process question, return routing results

### 3. Reader
- [x] Display book chapters with navigation
- [x] Text selection → highlight menu (highlight, note, ask)
- [x] Create/delete highlights (persisted to Supabase)
- [x] Annotations on highlights
- [x] Chat about selected text (Text Companion)
- [x] Routing context banner when arriving from ask

**Routes:**
- `GET /read/{book_id}` — Reader view
- `POST /read/{book_id}/highlight` — Create highlight
- `DELETE /read/{book_id}/highlight/{id}` — Delete highlight
- `POST /read/{book_id}/annotation` — Create annotation
- `DELETE /read/{book_id}/annotation/{id}` — Delete annotation
- `POST /read/{book_id}/chat` — Ask about selected text

### 4. Text Companion (Chat with Book)
- [x] ALWAYS answers (no more refusals)
- [x] Explains meaning, context, implications, historical background
- [x] Grounded in selected text but helpful
- [x] Works with real LLM (not just mock)

### 5. Library
- [x] Browse all books
- [x] Book detail page
- [x] Save/unsave books to "My Books"
- [x] Filter by domain

**Routes:**
- `GET /library/` — Browse books
- `GET /library/book/{book_id}` — Book detail
- `GET /library/my` — User's saved books
- `POST /library/save/{book_id}` — Save book
- `POST /library/unsave/{book_id}` — Unsave book

### 6. Wishlist (Book Requests)
- [x] Request new books
- [x] View user's requests
- [x] Cancel pending requests

**Routes:**
- `GET /wishlist/` — User's requests
- `POST /wishlist/request` — Submit request
- `POST /wishlist/cancel/{id}` — Cancel request

### 7. Admin
- [x] View all book requests
- [x] Approve/reject requests
- [x] Mark as added

**Routes:**
- `GET /admin/requests` — All requests
- `GET /admin/requests/{id}` — Request detail
- `POST /admin/requests/{id}/approve`
- `POST /admin/requests/{id}/reject`
- `POST /admin/requests/{id}/mark-added`

### 8. Database (Supabase)
- [x] All tables created: users, sessions, books, chapters, book_text, highlights, annotations, saved_books, book_requests
- [x] 11 real books with chapters in DB
- [x] REST API mode (no psycopg2 issues)

---

## 📊 CURRENT DATA

| Table | Count | Notes |
|-------|-------|-------|
| books | 11 | Real books with chapters |
| users | 2+ | Test users created |
| domains covered | ~8 | Philosophy, Strategy, Psychology, Technology, Economics, etc. |

---

## 🔧 WHAT NEEDS WORK FOR MVP

### High Priority (Must Have)

1. **Import 1300 Book Library**
   - Books must have: `id`, `title`, `author`, `domain`, `subdomain`
   - Each book needs chapters with offsets
   - Update taxonomy.py with real book IDs
   - Ingest script: `admin/ingest_books.py`

2. **Test Full User Flow End-to-End**
   - Register → Verify email → Login
   - Ask question → Get routing → Click recommendation
   - Read chapter → Highlight text → Ask about it
   - Save book → View in My Books
   - Request book → View in Wishlist

3. **Highlight Persistence for Logged-In Users**
   - Currently works but uses Supabase Auth user IDs (UUIDs)
   - Verify highlights persist across sessions
   - Verify they're scoped to user (can't see others' highlights)

### Medium Priority (Should Have)

4. **UI/UX Polish**
   - Loading states for LLM calls
   - Error handling with user-friendly messages
   - Mobile responsiveness
   - Keyboard shortcuts visible/documented

5. **Performance**
   - LLM response caching (routing_cache.py exists)
   - Book text lazy loading for large books

6. **Admin Experience**
   - Admin role check on admin routes
   - Better request management UI

### Low Priority (Nice to Have)

7. **PDF Downloads**
   - Generate PDF from book_text
   - Watermark with user info

8. **Reading Progress**
   - Track last read position
   - Resume reading

---

## 🗂 KEY FILES

### Services
- `app/services/agent_service.py` — Orchestrates LLM agents
- `app/services/canon_service.py` — Read-only book access
- `app/services/user_service.py` — User data (highlights, saved books)
- `app/services/request_service.py` — Book requests

### Agents
- `app/agents/intent_classifier.py` — Query → domains
- `app/agents/reading_router.py` — Domain → books/chapters
- `app/agents/text_companion.py` — Chat about selected text
- `app/agents/taxonomy.py` — Domain → book ID mappings

### Routes
- `app/routes/auth.py` — Supabase Auth
- `app/routes/ask.py` — Question routing
- `app/routes/reader.py` — Reader + highlights + chat
- `app/routes/library.py` — Browse/save books
- `app/routes/wishlist.py` — Book requests
- `app/routes/admin.py` — Admin tools

### Config
- `app/config.py` — All settings
- `.env` — Environment variables (not in git)

---

## 🔐 ENVIRONMENT VARIABLES NEEDED

```env
# Supabase
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...

# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini

# App
USE_MOCK_AGENTS=false
ENV=development
SECRET_KEY=your-secret-key
```

---

## 🚀 TO LAUNCH

1. Import your 1300 book library
2. Update taxonomy.py with all book IDs by domain
3. Set `ENV=production` and proper `SECRET_KEY`
4. Configure Supabase:
   - Site URL → production URL
   - Redirect URLs → `https://yourdomain.com/auth/confirm`
5. Deploy (Render, Fly.io, Vercel, etc.)

---

## 📝 RECENT COMMITS

```
e548247 Add resend confirmation email button after 20s countdown
aa5df60 Simplify verify email page - remove confusing button
795d6a9 Improve auth UX: user menu, verify email flow
40b0c32 Fix Text Companion to ALWAYS answer + Switch to Supabase Auth
87bf5f6 Fix query→domain→books pipeline and Text Companion
```

---

## 🎯 VISION REMINDER

> "We are building a platform where every book users want, they can either view in the library as a PDF and download, or make a request and get that book added to the library for everyone if approved. We are aggregators, middlemen, shovel salesmen, but also the shovelers."

The foundation is solid. Import the books, polish the UX, launch.
