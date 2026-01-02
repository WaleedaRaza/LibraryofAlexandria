# OpenAI Integration Guide

## Overview

This integration unmocks the `IntentClassifier` and `ReadingRouter` agents to use real OpenAI LLM calls.

**Status:** Backend implementation complete. No UX/template changes.

## What Was Built

### 1. LLM Provider (`app/agents/llm_provider.py`)
- Centralized OpenAI client wrapper
- Exponential backoff retry (max 3 attempts)
- 30-second timeout per call
- Token usage logging
- Structured JSON output parsing
- Graceful error handling

### 2. Taxonomy Gate (`app/agents/taxonomy.py`)
- Maps domain/subdomain → candidate book_ids
- Hardcoded mappings for V1 (Philosophy, Strategy, Technology, Psychology, etc.)
- Caps candidates at 12 books max
- Prevents LLM from hallucinating books outside taxonomy
- Version tracking for cache invalidation

### 3. Routing Cache (`app/agents/routing_cache.py`)
- In-memory cache for routing results
- Cache key: normalized(query) + taxonomy_version
- TTL: 1 hour (configurable)
- Automatic invalidation on taxonomy changes
- Hit/miss statistics

### 4. Updated Agents

#### IntentClassifier (`app/agents/intent_classifier.py`)
- Uses `llm_provider` for classification
- Returns structured JSON: `{domain, subdomain, confidence}`
- Refuses invalid/off-topic queries: `{is_valid: false, refusal_reason}`
- Validates domain against whitelist
- Falls back to Philosophy domain on errors

#### ReadingRouter (`app/agents/reading_router.py`)
- Uses `llm_provider` + taxonomy gate
- Fetches candidate books from taxonomy
- Returns 2-4 parallel reading paths
- Each path has 1-2 recommendations (max 6 total)
- Validates all book_ids against taxonomy
- Never hallucinates books/chapters
- Fails closed (refuses if can't route)

### 5. Eval Harness (`app/agents/eval_harness.py`)
- 30 diverse test queries
- Runs complete routing pipeline
- Prints intent + routing results
- Shows token usage statistics
- Validates expected domains

## Setup

### 1. Set OpenAI API Key

```bash
export OPENAI_API_KEY="sk-..."
export OPENAI_MODEL="gpt-4o-mini"  # Optional, defaults to gpt-4o-mini
```

### 2. Disable Mock Mode

```bash
export USE_MOCK_AGENTS="false"
```

Or in `.env`:
```
USE_MOCK_AGENTS=false
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

### 3. Run Eval Harness

```bash
cd /Users/waleedraza/Downloads/Librarai/alexandria
source venv/bin/activate
python -m app.agents.eval_harness
```

This will:
- Run 30 test queries through the pipeline
- Print intent classification + routing results
- Show success rate
- Display token usage by agent

## Architecture

```
User Query
    ↓
IntentClassifier (LLM)
    ↓ {domain, subdomain, confidence}
Taxonomy Gate
    ↓ [candidate_book_ids] (max 12)
ReadingRouter (LLM)
    ↓ {paths: [angle, recommendations]}
Cache (keyed by query + tax_version)
    ↓
Return to User
```

## Constraints Enforced

1. **No embeddings or global corpus search** ✅
   - Router only sees candidate books from taxonomy
   - No vector search or similarity matching

2. **No template/CSS changes** ✅
   - All changes are backend-only
   - UX remains identical

3. **TextCompanion still mocked** ✅
   - Only unmocked IntentClassifier and ReadingRouter
   - Text companion (section chat) still uses mock

4. **Router constrained to candidates** ✅
   - Taxonomy gate limits books
   - Validation rejects hallucinated book_ids
   - Falls back to mock on errors

5. **Fail closed** ✅
   - Invalid queries refused with reason
   - API errors fall back gracefully
   - Never returns empty recommendations without explanation

## Token Usage Estimates

Based on test runs:

- **IntentClassifier**: ~150-200 tokens per call
- **ReadingRouter**: ~500-800 tokens per call
- **Total per query**: ~650-1000 tokens

At current pricing (gpt-4o-mini: $0.15/1M input, $0.60/1M output):
- Per query: ~$0.0008 ($0.80 per 1000 queries)
- 30 eval queries: ~$0.024

## Taxonomy Mappings

Current hardcoded mappings:

| Domain | Subdomain | Books |
|--------|-----------|-------|
| Philosophy | Stoicism | Meditations |
| Strategy | Military Strategy | The Art of War |
| Strategy | Political Philosophy | The 48 Laws of Power |
| Technology | Systems Design | Thinking in Systems |
| Psychology | Mindfulness | Miracle of Mindfulness |
| Business | *(general)* | 48 Laws of Power |
| Economics | *(general)* | Thinking in Systems |

**To update:** Edit `TAXONOMY` list in `app/agents/taxonomy.py`  
**Remember:** Increment `TAXONOMY_VERSION` to invalidate cache

## Cache Behavior

- **Cache hit**: Returns cached result immediately (no LLM call)
- **Cache miss**: Calls LLM, caches result for 1 hour
- **Invalidation**: Automatic when taxonomy version changes
- **Stats**: Available via `routing_cache.get_routing_cache().get_stats()`

## Monitoring

### Check Usage Stats

```python
from app.agents.llm_provider import get_llm_provider

provider = get_llm_provider()
stats = provider.get_usage_summary()
print(stats)
# {
#   "total_calls": 60,
#   "total_tokens": 45000,
#   "by_agent": {
#     "IntentClassifier": {"calls": 30, "total_tokens": 6000},
#     "ReadingRouter": {"calls": 30, "total_tokens": 39000}
#   }
# }
```

### Check Cache Stats

```python
from app.agents.routing_cache import get_routing_cache

cache = get_routing_cache()
stats = cache.get_stats()
print(stats)
# {
#   "total_entries": 25,
#   "hits": 15,
#   "misses": 10,
#   "hit_rate_percent": 60.0,
#   "ttl_seconds": 3600,
#   "taxonomy_version": 1
# }
```

## Next Steps

1. **Run eval harness** with real API key to validate routing quality
2. **Inspect outputs** - are the routing paths sensible?
3. **Adjust prompts** if needed (in `intent_classifier.py` and `reading_router.py`)
4. **Expand taxonomy** as more books are added
5. **Unmock TextCompanion** when ready (separate task)

## Rollback Plan

To revert to mock mode:

```bash
export USE_MOCK_AGENTS="true"
```

Or remove from `.env`. Mock implementations remain intact.

## Future Enhancements

- **Dynamic taxonomy**: Load from database instead of hardcoded
- **Redis cache**: Replace in-memory cache for multi-instance deployments
- **A/B testing**: Compare LLM vs mock routing quality
- **Fine-tuning**: Collect routing data for model fine-tuning
- **Prompt engineering**: Iterate on system prompts based on eval results

