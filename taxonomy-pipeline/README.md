# Taxonomy Pipeline

PDF → Canonical Artifact JSON → (eventually) App Database

## Quick Start

```bash
# 1. Install dependencies
pip install -e .

# 2. Start Ollama and pull your model
ollama serve                    # in one terminal
ollama pull llama3.1:8b         # in another (or whatever model you want)

# 3. Verify LLM is working
python -m src.cli check-llm

# 4. Drop a test PDF into data/pdfs/
cp ~/some-book.pdf data/pdfs/

# 5. Process it
python -m src.cli process --pdf data/pdfs/some-book.pdf

# 6. Inspect the result
python -m src.cli inspect --artifact data/artifacts/some_book.json

# 7. Read a section
python -m src.cli read-section --artifact data/artifacts/some_book.json --section-id sec_001
```

## Switching Models

Edit `config.yaml`:
```yaml
llm:
  model: llama3.1:70b    # or mistral, phi3, etc.
```

Or pull and use any Ollama model — just make sure it supports JSON output.

## Re-running Stages

If boundary detection was bad, re-run from that stage (clears S4-S7 checkpoints):
```bash
python -m src.cli process --pdf data/pdfs/some-book.pdf --rerun-from s4_boundaries
```

## Batch Processing

```bash
python -m src.cli batch --pdf-dir data/pdfs/
```

Resumes automatically — skips books that already have artifacts.

## Project Structure

```
src/
  cli.py              # Entry point
  config.py           # Config loader
  schema.py           # Pydantic models (the artifact contract)
  llm.py              # Ollama client
  pipeline1/
    runner.py          # Orchestrator with checkpoint/resume
    s1_extraction.py   # PDF → raw text (PyMuPDF, no LLM)
    s2_cleaning.py     # Raw text → clean text (deterministic)
    s3_structure.py    # Classify book type (1 LLM call)
    s4_boundaries.py   # Find section breaks (N LLM calls, sliding window)
    s5_enrichment.py   # Summarize + tag each section (N LLM calls)
    s6_synthesis.py    # Book-level thematic index (1 LLM call)
    s7_validation.py   # Quality checks (no LLM)

data/
  pdfs/                # Input: drop PDFs here
  artifacts/           # Output: one JSON per book
  checkpoints/         # Stage-level resume points
  flagged/             # Symlinks to low-confidence artifacts
```

## Iterative Testing Workflow

1. Start with ONE book you know well (e.g. Meditations)
2. Run `process` and `inspect` the artifact
3. Check: does the clean text read right? (`read-section`)
4. Check: are section boundaries correct? (compare to real TOC)
5. Check: do themes and routing hints make sense?
6. If not → adjust prompts, config, or model → `--rerun-from` the broken stage
7. Repeat with 4 more books of different types before scaling
