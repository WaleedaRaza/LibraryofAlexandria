# Rayan — Start Here

You already saw the codebase. This doc is the map.

---

## The Point

User asks a question. We route them to the exact section of the actual book that answers it. They read, highlight, chat about the passage.

That's it. We're not summarizing books. We're not competing with Goodreads. We're competing with the impulse to ask ChatGPT and get a hallucinated paraphrase instead of reading the source.

The app works. It has one book (Metaphysics). Your job is to get hundreds of books in, and make the routing good enough that it actually sends people to the right place.

---

## Two Things, Not One

```
taxonomy-pipeline/          →     app/
(offline, runs on your Mac)       (the web app users see)

PDF → 7 stages → artifact.json → routes queries → reader
```

They share zero code. The only handoff is `artifact.json` files that live in `taxonomy-pipeline/data/artifacts/`.

Drop a new artifact there. The app picks it up automatically. No imports, no database writes for book content.

---

## Docs — What to Read for What

| Doc | Read it for |
|-----|------------|
| `ARCHITECTURE.md` | Full system map. Both systems, all layers, every data flow. Read this first. |
| `taxonomy-pipeline/README.md` | How to run the pipeline. Commands, stages, re-run flags. |
| `CURRENT_VS_DESIRED_STATE.md` | Where we are vs where we need to be. The gap list. |
| `DEPLOYMENT_ISSUES.md` | All 34 GitHub issues written out with acceptance criteria. |
| GitHub issues | Same issues with deep technical detail — implementation specs, code sketches, exact files to touch. Issues are more detailed than the doc. |

Don't read `manifest.md` yet — it's a long historical reference. Come back to it if you need background on a specific decision.

---

## What Needs Doing

### Phase 1: Get books in + make routing work

This is your entire focus. Don't touch auth, deployment, or brainrot until this is done.

**Pipeline hardening** (before running the full batch)

The pipeline as-is will take 40+ hours to process 500 books because S5 runs LLM calls sequentially. It also has no `--model` flag, no ETA display, and no failure tracking — so you'd be running blind with no way to retry failures.

Fix that before touching the corpus. Issues: **#5, #8, #35, #36**.

**Full corpus run**

You have ~550 PDFs. Run them. Review what fails. Issues: **#6, #7, #9**.

**Routing**

With 1 book the routing works fine. With 500 books it breaks — the router is hardcoded to look at 3 candidates, uses domain silos that hide cross-domain books, and ignores the `routing_hints` entirely. A question about Stoic acceptance shouldn't only surface if the user types the word "stoicism."

Fix that. Issues: **#37, #38, #10**.

---

## Issue Map

| Issue | What | Do When |
|-------|------|---------|
| #35 | Benchmark models — pick what to run the corpus with | First |
| #5 | Parallelize S5, add `--model` flag, ETA, failure manifest | Before corpus run |
| #36 | Harden S6 prompts so routing hints are useful | Before corpus run |
| #8 | Fix title/author stored in artifact (currently broken for all books except Metaphysics) | Before corpus run |
| #6 | Run full batch | After #5 done |
| #7 | `validate-all` CLI — quality report across all artifacts | After #6 |
| #9 | Review flagged artifacts, rerun fixable ones | After #7 |
| #37 | Global thematic index, fix cross-domain routing | After artifacts exist |
| #38 | Routing golden test suite | After #37 |
| #10 | Routing quality check | After #38 |

---

## One Rule

`text.content` inside each artifact is immutable. Every section offset, every highlight in the database, references character positions in that string. Re-run S2 cleaning on a processed book and you invalidate everything downstream.

If a book needs to be reprocessed, reprocess it from the beginning with `--rerun-from s1_extraction`. Don't patch individual stages on a book that already has user data.

---

## Done When

Type this into the app: *"I feel like nothing I do matters"*

Get 2+ reading paths pointing to specific sections in different books. Click one. Read the passage. Highlight something. Ask a question about it. Get an answer that references that exact text.

That's the product working. Get there with 50+ books.
