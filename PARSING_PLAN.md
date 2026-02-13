# Book Parsing & Ingestion Plan

## Current State

Based on manifest.md analysis:

- **552 PDFs** in `batch1books/`
- **518 extracted** to JSON (34 failed entirely)
- **31 ingested** into Supabase (487 missing!)
- **183 books (35%)** have single-chapter extraction (poor quality)
- **Extraction methods**: 67% regex, 3% TOC, 0% LLM, 29% fallback

## The Problem

The manifest describes a **Taxonomy Engine** using local LLMs for proper structural analysis, but the current pipeline uses regex/TOC which fails for 35% of books.

**Two paths forward:**

### Path A: Quick Win (Get All Books Ingested Now)
Use existing extraction pipeline, accept quality issues, ingest everything, fix quality later.

### Path B: Quality First (Fix Extraction Then Ingest)
Implement the manifest's Taxonomy Engine with local LLMs, re-extract all books properly, then ingest.

**Recommendation: Path A first, then Path B for books that need it.**

---

## Step 1: Verify Current State

```bash
# Check what's actually in the database vs what's extracted
python -m admin.verify_books --detailed
```

This will show:
- How many books are in database
- How many JSON files exist
- Which books are missing
- Which books have poor quality (single chapter)

---

## Step 2: Ingest All Extracted Books

**Goal:** Get all 518 extracted JSON files into the database, even if quality is imperfect.

```bash
# Ingest all JSON files (skips duplicates automatically)
python -m admin.ingest_from_json extracted/

# Or use the faster bulk version
python -m admin.bulk_ingest_fast extracted/
```

**Expected result:** All 518 books should be in database (minus any that truly failed extraction).

**Verify:**
```bash
python -m admin.verify_books
# Should show: Missing from DB: 0
```

---

## Step 3: Identify Books Needing Re-Extraction

**Criteria for re-extraction:**
1. Single chapter (fallback extraction)
2. Suspicious chapter count (too many = regex gone wild, too few = missed structure)
3. Known failures (Meditations, 1984, etc.)

**Script to identify:**
```bash
# This will list books that need re-extraction
python -m admin.verify_books --detailed | grep "single_chapter\|poor_quality"
```

**Manual review needed:**
- Books with 1 chapter → definitely need re-extraction
- Books with 50+ chapters → likely regex false positives
- Books you know have structure but show as single chapter

---

## Step 4: Re-Extract Poor Quality Books (Optional, Later)

The manifest describes a **Taxonomy Engine** with local LLMs. This is the proper solution but requires:

1. **Local LLM setup** (Ollama + Llama 3.1 8B or Qwen 2.5 7B)
2. **4-pass LLM pipeline** (structural analysis → boundaries → enrichment → synthesis)
3. **Time investment** (~17 hours for 500 books)

**For now:** Accept current extraction quality, get everything ingested, fix quality incrementally.

**When ready for quality upgrade:**
- Follow manifest Section 2.2 "System A: Taxonomy Engine"
- Re-extract flagged books with LLM pass
- Re-ingest improved JSON files

---

## Step 5: Verify Books Are Accessible

**Check that books appear in the app:**

```bash
# Start the app
uvicorn app.main:app --reload

# Then verify:
# 1. GET /library shows book cards
# 2. GET /library?domain=Philosophy filters correctly
# 3. GET /library/book/{id} shows book detail
# 4. GET /read/{id} opens reader
```

**Database queries to verify:**
```sql
-- Count books
SELECT COUNT(*) FROM books;

-- Count books with chapters
SELECT COUNT(DISTINCT book_id) FROM chapters;

-- Books with no chapters (problem!)
SELECT id, title, author FROM books 
WHERE id NOT IN (SELECT DISTINCT book_id FROM chapters);
```

---

## Step 6: Handle Extraction Failures

**34 PDFs failed extraction entirely.** These need manual intervention:

1. **Check extraction logs** (if they exist) for error messages
2. **Try manual extraction** with `extract_chapters.py` on individual files
3. **Check PDF quality** - may be corrupted, scanned images, or encrypted
4. **Decide:** Skip them or invest time fixing

**Script to identify failed PDFs:**
```bash
# Compare PDF count to JSON count
ls batch1books/*.pdf | wc -l  # Should be 552
ls extracted/*.json | wc -l    # Should be 518
# Missing = 34 failed
```

---

## Quick Start Commands

```bash
# 1. Verify current state
python -m admin.verify_books --detailed

# 2. Ingest all extracted books
python -m admin.bulk_ingest_fast extracted/

# 3. Verify all ingested
python -m admin.verify_books

# 4. Check app works
uvicorn app.main:app --reload
# Visit http://localhost:8000/library
```

---

## Success Criteria

✅ **All 518 extracted books are in database**  
✅ **Books appear in /library browse page**  
✅ **Books have chapters (even if imperfect)**  
✅ **Reader opens for any book**  
✅ **No books show as "single chapter" in production**

**Quality improvements can happen incrementally after deployment.**

---

## Notes

- **Don't wait for perfect extraction** - get everything ingested first
- **Single-chapter books are still readable** - just not navigable by chapter
- **The manifest's Taxonomy Engine is the long-term solution** - but it's a separate project
- **Current extraction is "good enough" for MVP** - users can still read and highlight
