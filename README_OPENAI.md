# OpenAI Integration - Quick Reference

## 🎯 What's Ready

✅ **IntentClassifier** - Unmocked, using OpenAI  
✅ **ReadingRouter** - Unmocked, using OpenAI  
✅ **Taxonomy Gate** - Limits books to ≤12 candidates  
✅ **Routing Cache** - 1-hour TTL, auto-invalidates  
✅ **Eval Harness** - 30 test queries  
✅ **No UX changes** - Backend only

## ⚡ Quick Test

```bash
# Terminal 1: Set API key
export OPENAI_API_KEY="sk-..."
export USE_MOCK_AGENTS=false

# Terminal 2: Test single query
cd alexandria
source venv/bin/activate
python test_routing.py "How do I deal with things I can't control?"

# Terminal 3: Run full eval (30 queries)
python -m app.agents.eval_harness
```

## 📁 New Files

```
app/agents/
├── llm_provider.py       ← OpenAI wrapper with retries
├── taxonomy.py           ← Domain → book_ids mapping
├── routing_cache.py      ← In-memory routing cache
├── intent_classifier.py  ← Updated to use LLM
├── reading_router.py     ← Updated to use LLM + taxonomy
└── eval_harness.py       ← 30 test queries

Root:
├── test_routing.py       ← Quick single-query test
├── test_openai.sh        ← Bash test script
├── OPENAI_INTEGRATION.md ← Full setup guide
├── DELIVERY_SUMMARY.md   ← Complete deliverables
└── README_OPENAI.md      ← This file
```

## 🔑 Environment Variables

```bash
# Required for LLM mode
export OPENAI_API_KEY="sk-..."

# Optional
export OPENAI_MODEL="gpt-4o-mini"  # default
export USE_MOCK_AGENTS="false"     # true = mock, false = LLM
```

## 🧪 Test Commands

```bash
# Mock mode (no API key needed)
USE_MOCK_AGENTS=true python test_routing.py

# Real LLM mode
USE_MOCK_AGENTS=false OPENAI_API_KEY="sk-..." python test_routing.py

# Full eval with 30 queries
./test_openai.sh real    # or just: ./test_openai.sh for mock
```

## 📊 Check Stats

```python
# Token usage
from app.agents.llm_provider import get_llm_provider
provider = get_llm_provider()
print(provider.get_usage_summary())

# Cache stats
from app.agents.routing_cache import get_routing_cache
cache = get_routing_cache()
print(cache.get_stats())

# Taxonomy coverage
from app.agents.taxonomy import get_taxonomy_coverage
print(get_taxonomy_coverage())
```

## 🎨 How It Works

```
Query: "Why does my boss act like that?"
    ↓
IntentClassifier (LLM)
    → domain="Strategy", subdomain="Political Philosophy"
    ↓
Taxonomy Gate
    → candidates=["book_062ae004ce4a"]  # 48 Laws of Power
    ↓
ReadingRouter (LLM)
    → paths=[{angle="Power dynamics", recs=[...]}]
    ↓
Cache (1 hour)
    ↓
Return to user
```

## 🛡️ Constraints

✅ No embeddings  
✅ No global search  
✅ Max 12 candidate books  
✅ Only books in taxonomy  
✅ 2-4 parallel paths  
✅ Max 6 recommendations  
✅ Fail closed (refuse, don't invent)

## 💡 Key Features

**LLM Provider:**
- 3 retries with backoff
- 30s timeout
- Token logging
- JSON validation

**Taxonomy:**
- Hardcoded mappings
- Version tracking
- Caps at 12 books

**Cache:**
- 1-hour TTL
- Query normalization
- Auto-invalidation

**Router:**
- Parallel paths (different angles)
- Validates book_ids
- Never hallucinates

## 📖 Read More

- **Setup:** `OPENAI_INTEGRATION.md`
- **Deliverables:** `DELIVERY_SUMMARY.md`
- **Test:** Run `./test_openai.sh`

## 🚨 Important

- **TextCompanion still mocked** (section chat not unmocked yet)
- **No template changes** (UX unchanged)
- **Taxonomy is hardcoded** (update in `taxonomy.py`)
- **Cache is in-memory** (use Redis for production)

---

**Status:** ✅ Ready to test  
**Cost:** ~$0.0008 per query (gpt-4o-mini)  
**Setup time:** 2 minutes

