# Taxonomy Artifacts Architecture

## Overview

This document describes the multi-layer taxonomy "dictionary architecture" for scalable routing without embeddings or global search.

**Key Principle:** Routing is deterministic and artifact-based. The system operates on pre-curated knowledge structures (artifacts) rather than dynamic corpus search.

## Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: Curated Taxonomy                                    │
│ taxonomy.v1.json                                             │
│ - Domains → Subdomains → Concepts                           │
│ - Human-curated knowledge structure                          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 2: Book Index (Generated)                             │
│ book_index.v{N}.json                                         │
│ - book_id → {title, author, domain_ids[], subdomain_ids[]}  │
│ - Generated from DB by admin script                          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 3: Chapter Index (Generated)                          │
│ chapter_index.v{N}.json                                      │
│ - chapter_id → {book_id, number, title, offsets, etc.}      │
│ - Generated from DB by admin script                          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 4: Taxonomy Gate (Runtime)                            │
│ app/agents/taxonomy_v2.py                                    │
│ - (domain_id, subdomain_id) → candidate_book_ids (≤12)      │
│ - book_ids → candidate_chapters                              │
│ - Deterministic, fast lookup                                 │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 5: Reading Router (LLM)                               │
│ app/agents/reading_router.py                                 │
│ - Given: question + candidates                               │
│ - Returns: 2-4 parallel reading paths                        │
│ - CONSTRAINED: Can only pick from candidates                 │
└─────────────────────────────────────────────────────────────┘
```

## Artifacts

### 1. Taxonomy (Curated)

**File:** `artifacts/taxonomy.v1.json`  
**Type:** Manual curation  
**Version:** Incremented when structure changes

```json
{
  "version": 1,
  "domains": {
    "philosophy": {
      "id": "philosophy",
      "name": "Philosophy",
      "subdomains": {
        "stoicism": {
          "id": "stoicism",
          "name": "Stoicism",
          "concepts": ["control_dichotomy", "virtue_ethics", ...]
        }
      }
    }
  }
}
```

**Purpose:** Stable knowledge structure that defines the conceptual space.

### 2. Book Index (Generated)

**File:** `artifacts/book_index.v{N}.json`  
**Type:** Auto-generated from DB  
**Version:** Auto-incremented on each build

```json
{
  "version": 1,
  "books": [
    {
      "book_id": "book_d9d95145167f",
      "title": "Meditations",
      "author": "Marcus Aurelius",
      "domain_ids": ["philosophy"],
      "subdomain_ids": ["stoicism"],
      "is_public": true,
      "created_at": "..."
    }
  ]
}
```

**Purpose:** Maps books to taxonomy nodes. Enables domain → books lookup.

### 3. Chapter Index (Generated)

**File:** `artifacts/chapter_index.v{N}.json`  
**Type:** Auto-generated from DB  
**Version:** Matches book_index version

```json
{
  "version": 1,
  "chapters": [
    {
      "chapter_id": "ch_xxx",
      "book_id": "book_d9d95145167f",
      "number": 1,
      "title": "Full Text",
      "start_offset": 0,
      "end_offset": 45234,
      "word_count": 9046,
      "headings": []
    }
  ]
}
```

**Purpose:** Provides chapter metadata for routing. Future: headings/blurbs for finer-grained routing.

## Admin Workflow

### Building Artifacts

```bash
cd alexandria
python -m admin.build_artifacts
```

**What it does:**
1. Reads from `data/alexandria.db`
2. Queries `books` and `chapters` tables
3. Maps books to taxonomy (currently hardcoded in script)
4. Generates `book_index.v{N}.json` and `chapter_index.v{N}.json`
5. Auto-increments version number

**When to rebuild:**
- New books added
- Book metadata changes
- Domain/subdomain mappings change

### Version Management

- **Taxonomy version:** Manual, incremented when taxonomy structure changes
- **Artifact version:** Auto-incremented on each build
- **Cache invalidation:** Keyed by artifact version

## Runtime Behavior

### Taxonomy Gate V2

```python
from app.agents.taxonomy_v2 import get_taxonomy_gate

gate = get_taxonomy_gate()  # Loads latest artifacts

# Get candidate books
book_ids = gate.get_candidate_books(
    domain_id="philosophy",
    subdomain_id="stoicism",
    max_books=12
)
# Returns: ["book_d9d95145167f"]

# Get candidate chapters
chapters = gate.get_candidate_chapters(
    book_ids=book_ids,
    max_chapters_per_book=8
)
# Returns: {book_id: [chapter_dicts...]}
```

**Features:**
- Fast in-memory lookup (artifacts loaded once)
- Deterministic (same input → same output)
- Validated (only returns books that exist in artifacts)
- Bounded (max 12 books, max 8 chapters per book)

### Reading Router Integration

The router is **backwards compatible**:
- Accepts human-readable domain names ("Philosophy")
- Internally maps to domain IDs ("philosophy")
- Uses taxonomy gate to get candidates
- LLM only sees candidates, never full corpus

```python
router = ReadingRouter()
result = router.route(
    question="How do I deal with things I can't control?",
    domain="Philosophy",        # Human-readable
    subdomain="Stoicism",       # Human-readable
    available_books=books,
    chapters_by_book=chapters
)
```

**Constraints enforced:**
- LLM prompt includes ONLY candidate books/chapters
- Validation rejects any book_id not in candidates
- Fails closed if no candidates found

## Domain Mapping

**Problem:** Agent contracts use human-readable names, but artifacts use stable IDs.

**Solution:** Bidirectional mapper in `app/agents/domain_mapper.py`

```python
from app.agents.domain_mapper import map_to_ids, map_to_names

# Agent returns "Philosophy", "Stoicism"
domain_id, subdomain_id = map_to_ids("Philosophy", "Stoicism")
# Returns: ("philosophy", "stoicism")

# For display
domain_name, subdomain_name = map_to_names("philosophy", "stoicism")
# Returns: ("Philosophy", "Stoicism")
```

This allows:
- Agent contracts unchanged (still use "Philosophy")
- Taxonomy operates on stable IDs ("philosophy")
- No breaking changes to UX/templates

## Testing

### Artifact Test Harness

```bash
cd alexandria
python test_taxonomy_artifacts.py
```

**Validates:**
1. ✓ Returns valid JSON structure
2. ✓ Returns 2-4 parallel paths
3. ✓ Each path has 1-2 recommendations
4. ✓ Total recommendations ≤ 6
5. ✓ All book_ids in candidates
6. ✓ All book_ids valid in taxonomy
7. ✓ Proper refusal handling

**Output:**
```
[1/10] How do I deal with things I can't control?
--------------------------------------------------------------------------------
Intent: Philosophy/Stoicism
Confidence: 85.00%
Paths: 2
  → Foundational understanding
     Meditations (Ch1)
✓ VALIDATION PASSED
   Paths: 2
   Recommendations: 2
```

### Mock vs Real Testing

```bash
# Test with mock agents (no API key needed)
USE_MOCK_AGENTS=true python test_taxonomy_artifacts.py

# Test with real OpenAI
USE_MOCK_AGENTS=false OPENAI_API_KEY="sk-..." python test_taxonomy_artifacts.py
```

## Migration from V1 (Hardcoded)

The system automatically falls back to V1 if artifacts are missing:

```python
# In reading_router.py
try:
    from .taxonomy_v2 import get_taxonomy_gate
    USE_TAXONOMY_V2 = True
except (FileNotFoundError, Exception):
    from .taxonomy import get_candidate_books, validate_book_id
    USE_TAXONOMY_V2 = False
```

**To migrate:**
1. Create `artifacts/taxonomy.v1.json` (already done)
2. Run `python -m admin.build_artifacts`
3. Verify `artifacts/book_index.v1.json` and `chapter_index.v1.json` exist
4. Run `python test_taxonomy_artifacts.py`
5. If tests pass, V2 is active automatically

## Scaling Strategy

### Current (V1)
- 5 books
- Hardcoded mappings
- Single taxonomy version
- O(1) lookup (fast enough)

### With Artifacts (V2)
- 100s of books
- Generated mappings
- Versioned artifacts
- O(1) lookup with indexing
- **Still no embeddings or vector search**

### Future (V3+)
- 1000s of books
- Multi-taxonomy support (different users see different taxonomies)
- Concept-level routing (not just domain/subdomain)
- Chapter headings/blurbs for finer routing
- **Still deterministic, artifact-based**

## Hard Constraints (Preserved)

✅ **No embeddings:** Routing is dictionary lookup, not similarity search  
✅ **No global search:** LLM never sees full corpus, only candidates  
✅ **No template changes:** All routing logic is backend-only  
✅ **Deterministic:** Same query + taxonomy version → same candidates  
✅ **Fail closed:** If no candidates, refuse (don't invent)  
✅ **Bounded:** Max 12 candidate books, max 6 final recommendations

## Benefits

1. **Scalable:** Add 100s of books without changing routing logic
2. **Maintainable:** Taxonomy curated separately from code
3. **Auditable:** All mappings in JSON, easy to inspect
4. **Cacheable:** Version-based cache invalidation
5. **Testable:** Artifact-based tests don't depend on DB state
6. **Flexible:** Multiple taxonomies possible (user-specific, domain-specific)
7. **Fast:** In-memory lookups, no DB queries in routing loop

## Files Created

```
alexandria/
├── artifacts/
│   ├── taxonomy.v1.json          ← Curated taxonomy tree
│   ├── book_index.v1.json        ← Generated book mappings
│   └── chapter_index.v1.json     ← Generated chapter metadata
│
├── admin/
│   └── build_artifacts.py        ← Admin script to generate artifacts
│
├── app/agents/
│   ├── taxonomy_v2.py            ← Artifact-based taxonomy gate
│   ├── domain_mapper.py          ← Name ↔ ID bidirectional mapper
│   ├── reading_router.py         ← Updated to use V2 (with V1 fallback)
│   └── routing_cache.py          ← Updated to use artifact version
│
├── test_taxonomy_artifacts.py    ← Validation test harness
└── TAXONOMY_ARTIFACTS.md         ← This document
```

## Next Steps

1. ✅ Create taxonomy.v1.json
2. ✅ Create artifact builder script
3. ✅ Create taxonomy_v2.py
4. ✅ Update reading_router.py
5. ✅ Create test harness
6. ⏭️ Run artifact builder: `python -m admin.build_artifacts`
7. ⏭️ Run tests: `python test_taxonomy_artifacts.py`
8. ⏭️ Add more books, update mappings, rebuild artifacts
9. ⏭️ Iterate on taxonomy structure based on usage

---

**Status:** Architecture implemented, ready for artifact generation  
**Backwards Compatible:** Yes, falls back to V1 if artifacts missing  
**Breaking Changes:** None (UX unchanged, agent contracts preserved)
