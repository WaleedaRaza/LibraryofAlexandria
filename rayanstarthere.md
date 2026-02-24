# Rayan — Start Here

> This is your briefing. Read it in full before touching any code.

---

## What Alexandria Actually Is

Alexandria is not a book recommendation site. Book recommendation sites tell you "you might like Meditations." We don't do that.

Alexandria is a **routing engine for primary sources**. A user asks a real question — "how do I stop being destroyed by things I can't control?" — and we point them to the *exact section* of the *actual text* where Epictetus or Marcus Aurelius answers that. Not a summary. Not a review. The passage itself. Then we let them read it, highlight it, ask questions about it, and take notes on it.

Why this matters: every AI you can use online was trained on what people *say about* books. It was not trained on the books themselves. When you ask GPT what Marcus Aurelius says about grief, you get a synthesized paraphrase of a hundred SparkNotes pages. We send you to Book V.8 and let Aurelius speak for himself.

**The constraint is the product.** If a user can walk away without reading, we failed.

---

## The Two Systems

There are exactly two systems. They share zero code. They communicate through one file format: the artifact JSON.

```
SYSTEM A: Taxonomy Pipeline          SYSTEM B: Reading Platform
(your machine, offline, Ollama)      (web app, FastAPI, serves users)

PDF → 7-stage pipeline            artifact JSON → route → read
→ artifact JSON per book    ───►  highlights, chat, notes
```

**Your job right now is System A entirely.** System B is working but starved — it has 1 book. Your job is to feed it hundreds.

---

## System A: The Taxonomy Pipeline

**Location:** `taxonomy-pipeline/`

The pipeline takes a PDF and produces one `artifact.json` per book. That artifact is the canonical representation of the book — full clean text, section structure with character offsets, summaries, themes, and routing hints. Everything System B needs.

### The 7 Stages

```
PDF
 │
 ▼
S1: Extraction (PyMuPDF, no LLM)
    Raw text + page boundaries + TOC if present
 │
 ▼
S2: Cleaning (deterministic, no LLM)
    Strip headers/footers, fix hyphenation, normalize whitespace
    Produces content_hash — ALL OFFSETS REFERENCE THIS STRING FOREVER
 │
 ▼
S3: Structure (1 LLM call)
    Classify: book_type, hierarchy, front/back matter
 │
 ▼
S4: Boundaries (regex first, LLM fallback)
    Find section breaks → list of sections with char offsets
    Regex handles ~70% of books (well-structured classics)
    LLM sliding window handles the rest (poetry, essays, unmarked texts)
 │
 ▼
S5: Enrichment (1 LLM call per section) ← BOTTLENECK
    Per section: summary, key_themes, notable_passages, difficulty
    20-chapter book = 20 sequential calls
 │
 ▼
S6: Synthesis (1 LLM call per book)
    Book-level: domain, thematic_index, routing_hints, cross_references
    routing_hints.good_for is what the router uses to match user queries
 │
 ▼
S7: Validation (no LLM)
    Offset coverage, no gaps/overlaps, enrichment complete, confidence score
 │
 ▼
artifact.json
```

### The Canonical Artifact

```json
{
  "book_id": "meditations__marcus_aurelius",
  "title": "Meditations",
  "author": "Marcus Aurelius",
  "text": {
    "content": "THE FULL CLEAN TEXT — never modify this after creation",
    "content_hash": "sha256:..."
  },
  "sections": [
    {
      "id": "sec_012",
      "title": "Book V",
      "start_offset": 48221,
      "end_offset": 61400,
      "summary": "Marcus examines the discipline of the will...",
      "key_themes": ["self_discipline", "acceptance", "morning_routine"],
      "difficulty": "moderate"
    }
  ],
  "synthesis": {
    "domain": "philosophy",
    "subdomains": ["stoicism", "ethics"],
    "thematic_index": {
      "acceptance": ["sec_004", "sec_012", "sec_019"],
      "death": ["sec_006", "sec_014"]
    },
    "routing_hints": {
      "good_for": [
        "feeling like you have no control over what happens to you",
        "dealing with anger at others and wanting to let it go",
        "trying to stay focused when everything feels chaotic"
      ],
      "not_good_for": [
        "practical financial decisions",
        "technical skill development"
      ]
    }
  }
}
```

**The golden rule:** `text.content` is immutable. Every `start_offset` and `end_offset` in every section, every notable passage — they all reference character positions in this string. If you re-run S2 cleaning on an already-processed book, all downstream data is invalidated. Don't do it unless you're rerunning the whole book from scratch.

---

## What's Wrong With the Pipeline Right Now

### Problem 1: S5 is serial and slow

`s5_enrichment.py` runs LLM calls per section in a plain Python `for` loop. Each section is independent — there is no shared state between them. But they run one at a time.

A book with 20 chapters = 20 sequential calls × ~5s each = ~100 seconds just for enrichment. At this rate, 500 books takes 40+ hours.

**Fix:** `ThreadPoolExecutor` with 4 workers. Section enrichment calls are I/O-bound (HTTP to Ollama). Parallelizing them is safe and cuts time by 4x.

This is **issue #5**. Do this before running the full batch.

### Problem 2: No --model flag

Switching models requires editing `config.yaml`. Should be a CLI flag. This matters because the right model choice affects every artifact you produce.

**Fix:** Add `--model` option to both `process` and `batch` commands. One line in `cli.py`.

Also **issue #5**.

### Problem 3: No ETA, no failure manifest

The batch runner prints to terminal and loses failures. 10 hours in you have no idea how many books are done or what failed.

**Fix:** Rolling ETA after each book. Write failures to `data/batch_failures.json`. Add `--retry-failed` flag.

Also **issue #5**.

### Problem 4: title/author derivation is broken for anything except Metaphysics

`artifact_loader.py` has one hardcoded entry (`metaphysics_aristotle`) and a brittle string parser for everything else. With 500 books this breaks on basically everything.

**Fix:** Store `title` and `author` directly in the artifact JSON. Add fields to `schema.py`, populate them from the PDF filename in `runner.py`.

**Issue #8**.

### Problem 5: routing_hints.good_for is generic on weaker models

The S6 synthesis prompt produces useful routing hints on strong models and useless ones on weak models. "Understanding philosophy" is not a routing hint. "Feeling like nothing you do matters" is.

**Fix:** Harden the S6 prompt with explicit good/bad examples. Add post-parse validation that flags generic hints.

**Issue #36**.

### Problem 6: The router only looks at 3 books

`reading_router.py` caps candidates at `available_books[:3]`. With 500 books, 497 are invisible to every query. And domain filtering means cross-domain books never surface even when they'd be perfect.

**Fix:** Build a global thematic index at startup. Pre-filter candidates using theme word overlap, not domain classification. Raise cap to 20.

**Issue #37**.

---

## Your Work, In Order

### Week 1 — Setup + First Book

1. Read these files in this order:
   - `ARCHITECTURE.md`
   - `taxonomy-pipeline/README.md`
   - `taxonomy-pipeline/src/schema.py` — memorize the data structures
   - `taxonomy-pipeline/src/pipeline1/runner.py` — understand the orchestrator
   - `taxonomy-pipeline/src/pipeline1/s5_enrichment.py` — the bottleneck

2. Get Ollama running. Pull `qwen2.5:14b` if you have ≥16GB RAM, otherwise `llama3.1:8b`.

3. Run the pipeline on one book you know well:
   ```bash
   cd taxonomy-pipeline
   pip install -e .
   ollama serve  # in another terminal
   python -m src.cli process --pdf data/pdfs/meditations.pdf
   python -m src.cli inspect --artifact data/artifacts/meditations.json
   ```

4. Read the artifact. Are the section boundaries correct? Do the summaries make sense? Are the routing hints useful or generic?

5. Run the app and verify the book appears:
   ```bash
   cd ..
   pip install -r requirements.txt
   uvicorn app.main:app --reload --port 5000
   # Open http://localhost:5000
   # Ask: "how do I stop being upset by things outside my control?"
   # Should route to Meditations
   ```

### Week 2 — Pipeline Hardening (Issues #5, #8, #35, #36)

Before running 500 books, the pipeline needs to be production-ready. In this order:

**Issue #35 first:** Benchmark `llama3.1:8b` vs `qwen2.5:14b` on 3 books. Pick your model. Document it. Don't skip this — the model choice affects every artifact you produce for the rest of the project.

**Issue #5 next:** Parallelize S5, add `--model` flag, add ETA + failure manifest. This cuts your full batch time from 40+ hours to ~20 hours.

**Issue #36:** Harden the S6 synthesis prompt. Run your 3 benchmark books again with the new prompt. Confirm routing hints are human-readable scenarios, not academic categories.

**Issue #8:** Fix title/author storage. Add fields to schema, populate from PDF filename, update artifact_loader.

### Week 3 — Full Corpus Run (Issues #6, #7, #9)

With the pipeline hardened:

**Issue #6:** Run the full batch. Let it run overnight. Check the failure manifest in the morning.

**Issue #7:** Build `validate-all` CLI command. Run it on your artifact directory. Look at the distribution — how many pass (≥0.7 confidence), how many need review?

**Issue #9:** Triage flagged artifacts. Rerun the fixable ones. Document what's permanently skipped.

### Week 4 — Routing (Issues #37, #38, #10)

With 100+ good artifacts:

**Issue #37:** Build global thematic index. Fix the candidate cap. Fix cross-domain surfacing.

**Issue #38:** Write the routing golden test suite (≥25 test cases). Run it. Fix failures.

**Issue #10:** Full routing quality check. Document which queries route well, which don't, and why.

---

## How to Run the App

```bash
# Install dependencies
pip install -r requirements.txt

# Run
uvicorn app.main:app --reload --port 5000

# Artifacts must exist at:
# taxonomy-pipeline/data/artifacts/{book_id}.json

# The app loads them automatically — no database import needed
```

Environment variables (set in `.env` or export):
```bash
USE_MOCK_AGENTS=true   # uses keyword routing, no OpenAI needed
DEBUG=true
SECRET_KEY=dev-key-anything
```

---

## Key Files to Know

| File | What It Does |
|------|-------------|
| `taxonomy-pipeline/src/schema.py` | The data contract. Every field in the artifact. |
| `taxonomy-pipeline/src/pipeline1/runner.py` | Orchestrates all 7 stages. Checkpoint/resume logic here. |
| `taxonomy-pipeline/src/pipeline1/s5_enrichment.py` | The bottleneck. Parallelize this first. |
| `taxonomy-pipeline/src/pipeline1/s6_synthesis.py` | Routing hints come from here. Prompt quality matters. |
| `taxonomy-pipeline/src/cli.py` | All CLI commands. Add `--model`, `validate-all`, `test-routing` here. |
| `app/services/artifact_loader.py` | Reads artifact JSONs into the app. The bridge between pipeline and platform. |
| `app/agents/reading_router.py` | The routing logic. Mock and LLM paths both here. |
| `app/agents/intent_classifier.py` | Maps user question → domain(s). |
| `app/services/agent_service.py` | Orchestrates intent → routing → paths. |

---

## The Things That Cannot Break

**Do not change section IDs (`sec_001`, `fm_001`, etc.) after a book is ingested.** They are referenced by the thematic index and by user highlights in the database. Changing them orphans highlights.

**Do not re-run S2 cleaning on a book that already has user data** (highlights, annotations, chat). S2 changes `text.content`, which changes all offsets, which makes every stored highlight reference the wrong text.

**Do not change `CanonicalArtifact` field names** without updating `artifact_loader.py` at the same time. The app reads these fields directly.

---

## The Success Condition for Your Work

When you're done with Phase 1 (pipeline + routing), this should work perfectly:

1. Open the app
2. Type: "I feel like nothing I do matters and I can't stop caring what other people think of me"
3. Get 2-4 reading paths pointing to specific sections across ≥2 books
4. Click a path, read the actual passage
5. Highlight a sentence, ask "what does this mean?"
6. Get a grounded explanation referencing that exact passage

That's it. That's the whole product. Get that working with 50+ books and you've done your job.

---

## GitHub Issues Summary

| # | Title | Priority |
|---|-------|----------|
| #5 | Configure taxonomy batch: parallelism, --model flag, ETA, failure manifest | **Do first** |
| #35 | Model benchmarking: pick the right model | **Do before full batch** |
| #36 | Harden S6 synthesis prompts | **Before full batch** |
| #8 | Fix title/author storage in artifacts | **Before full batch** |
| #6 | Run full corpus batch (~500 books) | After #5 done |
| #7 | Build validate-all CLI command | After #6 done |
| #9 | Human review of flagged artifacts | After #7 done |
| #37 | Global thematic index + fix cross-domain routing | After artifacts exist |
| #38 | Routing golden test suite | After #37 done |
| #10 | Routing quality check across genres | After #38 done |

Do not touch Phase 2 (auth, wishlist), Phase 3 (brainrot), or Phase 4 (deployment) until Phase 1 is complete and routing is demonstrably working.

---

*The library is only as good as its artifacts. The routing is only as good as what the pipeline wrote into them. Start there.*
