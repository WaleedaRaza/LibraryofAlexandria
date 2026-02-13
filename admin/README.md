# Admin Scripts

CLI tools for ingestion, extraction, and maintenance. Run from project root.

---

## Taxonomy / Artifacts

| Script | Purpose |
|--------|---------|
| `taxonomy_engine.py` | Orchestrates taxonomy pipeline stages. |
| `build_artifacts.py` | Build canonical artifacts from pipeline output. |
| `bootstrap_artifacts.py` | Bootstrap artifact data. |
| `ingest_from_json.py` | Ingest from extracted JSON. |
| `bulk_ingest_fast.py` | Batch ingest. |
| `verify_books.py` | Verify ingested books. |
| `test_taxonomy_setup.py` | Test taxonomy setup. |

---

## Extraction (Legacy)

| Script | Purpose |
|--------|---------|
| `extract_chapters.py` | Extract chapter structure from PDFs. |
| `extract_pages.py` | Extract pages. |
| `ingest_books.py` | Ingest PDFs into DB. |
| `llm_chapter_pass.py` | LLM-based chapter detection. |
| `categorize_books.py` | Categorize books. |
| `update_pdf_paths.py` | Update PDF paths in DB. |

---

## Database

| Script | Purpose |
|--------|---------|
| `apply_schema_v2.py` | Apply schema_v2 migrations. |
| `seed_books.py` | Seed book data. |

---

**Note:** The primary ingestion path is now **taxonomy-pipeline** (see `taxonomy-pipeline/README.md`). Admin scripts here support legacy workflows and DB operations.
