# Taxonomy Artifacts - Quick Start

## What It Is

A **scalable, artifact-based routing system** that maps user queries to relevant book chapters through a curated taxonomy—without embeddings or global search.

## Architecture in 3 Layers

```
1. taxonomy.v1.json        ← Curated: domains → subdomains → concepts
2. book_index.v1.json      ← Generated: book_id → domain_ids
3. chapter_index.v1.json   ← Generated: chapter_id → metadata
```

## How It Works

```
Query: "How do I deal with things I can't control?"
  ↓
Intent: Philosophy / Stoicism
  ↓
Taxonomy Gate: philosophy + stoicism → [book_d9d95145167f, ...]  (≤12)
  ↓
Router: Picks 2-4 paths from candidates only
  ↓
Result: Parallel reading recommendations
```

## Quick Commands

### Rebuild Artifacts (When Books Change)
```bash
cd alexandria
source venv/bin/activate
python -m admin.build_artifacts
```

### Test the System
```bash
# Mock mode
USE_MOCK_AGENTS=true python test_taxonomy_artifacts.py

# With OpenAI
USE_MOCK_AGENTS=false OPENAI_API_KEY="sk-..." python test_taxonomy_artifacts.py
```

### Check Stats
```bash
python -c "
from app.agents.taxonomy_v2 import get_taxonomy_gate
gate = get_taxonomy_gate()
print(gate.get_stats())
"
```

## Current State

✅ **193 books indexed**  
✅ **6 domains** (Philosophy, Strategy, Psychology, Technology, Economics, Business)  
✅ **18 subdomains** (Stoicism, Military, Mindfulness, Systems, etc.)  
✅ **Version 1** artifacts generated  
✅ **All tests passing** (10/10 queries)

## Key Files

```
artifacts/
  taxonomy.v1.json       ← Edit this to change taxonomy structure
  book_index.v1.json     ← Auto-generated (don't edit)
  chapter_index.v1.json  ← Auto-generated (don't edit)

admin/
  build_artifacts.py     ← Run this to rebuild indices

app/agents/
  taxonomy_v2.py         ← Runtime gate (loads artifacts)
  domain_mapper.py       ← Maps "Philosophy" ↔ "philosophy"
  reading_router.py      ← Uses taxonomy gate
```

## Constraints (Still Enforced)

✅ No embeddings  
✅ No global search  
✅ Max 12 candidate books  
✅ Max 6 final recommendations  
✅ Deterministic routing  
✅ Fail closed (refuse, don't invent)

## When to Rebuild

Rebuild artifacts when:
- New books added to DB
- Book metadata changes
- Domain/subdomain mappings change (edit `admin/build_artifacts.py`)

**Version auto-increments**, cache auto-invalidates.

## Backwards Compatibility

**V2 (artifacts)** used if artifacts exist  
**V1 (hardcoded)** used if artifacts missing

No breaking changes. Agent contracts unchanged.

## Read More

- **TAXONOMY_ARTIFACTS.md** - Full architecture
- **ARTIFACT_DELIVERY.md** - Complete delivery summary
- **OPENAI_INTEGRATION.md** - LLM setup guide

---

**Status:** Ready for production  
**Setup time:** 2 minutes  
**Books indexed:** 193  
**No UX changes**
