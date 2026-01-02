# Alexandria Feature Status Report

**Date**: January 1, 2026
**Environment**: Local (localhost:5050)
**LLM Mode**: Enabled (GPT-4o-mini)

---

## Executive Summary

All three LLM-powered agents work correctly:
- ✅ **Intent Classifier** - Correctly routes questions to domains
- ✅ **Reading Router** - Returns intelligent parallel reading paths
- ✅ **Text Companion** - Explains text contextually, refuses off-topic

All core flows functional:
- ✅ Ask → Route → Read
- ✅ Library browse + search
- ✅ Reader with text selection
- ✅ Highlight creation
- ✅ Chat with selected text
- ✅ Auth (register/login)
- ✅ Wishlist (with auth gate)

---

## Detailed Feature Tests

### 1. LLM Agents

#### Intent Classifier
| Test | Result |
|------|--------|
| Philosophy question → Philosophy domain | ✅ Works |
| Strategy question → Strategy domain | ✅ Works |
| Off-topic question → Refusal | ✅ "Not covered by specified domains" |
| Crypto/finance question → Refusal | ✅ Clear rejection message |

#### Reading Router
| Test | Result |
|------|--------|
| Returns 2-4 parallel paths | ✅ Works (tested: 3 paths) |
| Each path has distinct "angle" | ✅ "Competitive Advantage", "Historical Context", etc. |
| Recommendations match domain | ✅ Strategy question → Strategy books |
| Rationales explain WHY | ✅ Contextual explanations |
| Links work | ✅ `/read/{book_id}?chapter=N` |

#### Text Companion
| Test | Result |
|------|--------|
| Explains selected text | ✅ "government of temper" = emotional regulation |
| Refuses personal advice | ✅ "I cannot provide personal advice" |
| Refuses modern application | ✅ Correctly constrains response |
| Handles errors gracefully | ✅ Returns refusal on failure |

---

### 2. Core User Flows

#### Ask Flow
```
[Homepage] → [Type question] → [Submit]
                                   ↓
                          [Routing Results Page]
                                   ↓
                      [2-4 parallel reading paths]
                                   ↓
                          [Click "Read this section"]
                                   ↓
                          [Reader opens at chapter]
```
**Status**: ✅ Complete end-to-end

#### Library Flow
```
[/library] → [See 100 books] → [Filter by domain]
                                   ↓
                          [Click book card]
                                   ↓
                          [Book detail page]
                                   ↓
                          [Start reading]
```
**Status**: ✅ Complete

#### Reader Flow
```
[/read/{id}?chapter=N] → [Text loads] → [Select text]
                                              ↓
                                    [Popup menu appears]
                                              ↓
                          [🖍️ Highlight] [📝 Note] [💬 Chat]
```
**Status**: ✅ Works (note: highlights don't persist visually on reload)

#### Chat Flow
```
[Select text] → [Click 💬] → [Chat panel opens]
                                   ↓
                          [Type question] → [Submit]
                                   ↓
                          [LLM response appears]
```
**Status**: ✅ Complete with LLM

#### Auth Flow
```
[/auth/register] → [Fill form] → [Submit] → [Redirect to home]
[/auth/login] → [Fill form] → [Submit] → [Session cookie set]
[/auth/logout] → [Session cleared]
```
**Status**: ✅ Complete

#### Wishlist Flow
```
[/wishlist] → [Requires auth] → [Shows 401 if not logged in]
                                   ↓
                          [With auth: Show requests]
                                   ↓
                          [Submit request] → [Pending status]
```
**Status**: ✅ Works (auth gate correct)

---

### 3. Known Issues

#### Critical (Must Fix Before Deploy)

| Issue | Impact | Location |
|-------|--------|----------|
| Highlights don't render on reload | UX broken - user work disappears | `reader.py`, `reader.html` |
| Annotations don't display | Same as above | `reader.py`, `reader.html` |
| SHA256 passwords | Security risk | `auth.py` |
| No `/health` endpoint | Deployment monitoring | `main.py` |
| SQLite only | Can't deploy to serverless | `database.py` |

#### Important (Should Fix)

| Issue | Impact | Location |
|-------|--------|----------|
| No admin routes | Ops burden | Need to create |
| Cookie not Secure in prod | Security | `auth.py` |
| Duplicate books in DB | UX clutter | 193 books, many dupes |
| Single chapter per book | Limited navigation | `ingest_books.py` |

#### Minor (Can Defer)

| Issue | Impact | Location |
|-------|--------|----------|
| No loading states | UX polish | Templates/JS |
| No email validation | Spam signups | `auth.py` |
| /library redirect (307) | Minor UX | Route config |

---

### 4. LLM Cost Estimate

Based on test runs:

| Agent | Tokens/Call (approx) | Cost/1000 calls |
|-------|---------------------|-----------------|
| Intent Classifier | ~200 | ~$0.06 |
| Reading Router | ~600 | ~$0.18 |
| Text Companion | ~350 | ~$0.10 |

With GPT-4o-mini at $0.15/1M input, $0.60/1M output:
- **1000 ask flows**: ~$0.25
- **1000 chat queries**: ~$0.10
- **Daily budget $1**: Supports ~3000 interactions

---

### 5. Feature Completion Matrix

| Feature | Backend | Frontend | LLM | Persist | Display | Tested |
|---------|---------|----------|-----|---------|---------|--------|
| Ask/Route | ✅ | ✅ | ✅ | N/A | ✅ | ✅ |
| Library | ✅ | ✅ | N/A | ✅ | ✅ | ✅ |
| Reader | ✅ | ✅ | N/A | ✅ | ✅ | ✅ |
| Highlight | ✅ | ⚠️ | N/A | ✅ | ❌ | ⚠️ |
| Annotation | ✅ | ⚠️ | N/A | ✅ | ❌ | ⚠️ |
| Chat | ✅ | ✅ | ✅ | N/A | ✅ | ✅ |
| Save Book | ✅ | ✅ | N/A | ✅ | ✅ | ✅ |
| Wishlist | ✅ | ✅ | N/A | ✅ | ✅ | ⚠️ |
| Auth | ✅ | ✅ | N/A | ✅ | ✅ | ✅ |
| Admin | ❌ | ❌ | N/A | N/A | N/A | ❌ |

Legend: ✅ Complete | ⚠️ Partial | ❌ Missing

---

### 6. Recommendation

**The LLM core is solid.** All three agents work correctly with proper constraints and refusals.

**Prioritized fix order:**

1. **Highlight/Annotation Display** (2-3 hours)
   - Load user's highlights on GET /read/{id}
   - Render in annotations rail
   - This is the #1 user trust issue

2. **Security Baseline** (1 hour)
   - bcrypt passwords
   - Secure cookies in production

3. **Health Endpoint** (15 min)
   - Add /health route
   - Return DB status

4. **Admin Dashboard** (4 hours)
   - View/approve/reject requests
   - Basic but functional

5. **Postgres Migration** (2 hours)
   - Then deploy

---

### 7. What's Ready vs What's Not

**Ready to ship (locally):**
- Ask → Route → Read flow
- Library browsing
- Reading experience
- Text chat
- Auth
- Highlight creation (backend)
- Wishlist submission

**Not ready:**
- Highlight/annotation display on reload
- Admin operations via web
- Production database
- Production security

---

*Generated from live testing on localhost:5050*
