# Alexandria — Documentation Index

Start here for context. Documents are ordered by onboarding sequence.

---

## Onboarding

| Document | Purpose |
|----------|---------|
| **[NEW_DEV_PRESENTATION.md](../NEW_DEV_PRESENTATION.md)** | Origin story, vision, current vs desired state, codebase guide. **Read this first.** |
| [manifest.md](../manifest.md) | Full architecture, user flows, feature spec, sequencing. Deep reference. |
| [taxonomy.md](../taxonomy.md) | Taxonomy pipeline architecture, artifact schema, stage design. |

---

## Setup & Operations

| Document | Purpose |
|----------|---------|
| [README.md](../README.md) | Quick start, project structure, deploy. |
| [TAXONOMY_SETUP.md](../TAXONOMY_SETUP.md) | Taxonomy pipeline setup. |
| [taxonomy-pipeline/README.md](../taxonomy-pipeline/README.md) | Pipeline CLI, stages, config. |
| [SMOKE_TESTS.md](../SMOKE_TESTS.md) | Smoke test procedures. |
| [render.yaml](../render.yaml) | Render.com deployment config. |

---

## Reference

| Document | Purpose |
|----------|---------|
| [PARSING_PLAN.md](../PARSING_PLAN.md) | Parsing approach (legacy). |
| [PARSING_STATUS.md](../PARSING_STATUS.md) | Extraction status. |

---

## Key Paths in the Codebase

```
app/main.py              → Entry point
app/routes/ask.py        → Ask flow
app/routes/reader.py     → Reader, highlights, chat
app/services/artifact_loader.py  → Artifact JSON access
app/agents/reading_router.py    → Section routing
static/js/reader.js      → Client-side highlights
```
