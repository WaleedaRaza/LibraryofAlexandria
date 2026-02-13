# Taxonomy Engine Setup Guide

## Prerequisites

1. **Mac with M-series chip** (M1/M2/M3) - recommended for local LLM performance
2. **Python 3.9+**
3. **8GB+ RAM** (for running local LLM)

## Step 1: Install Ollama

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Or download from: https://ollama.com/download
```

## Step 2: Pull LLM Model

The manifest recommends **Llama 3.1 8B Instruct** (Q4 quantized) or **Qwen 2.5 7B**.

```bash
# Start Ollama server (if not already running)
ollama serve

# In another terminal, pull the model
ollama pull llama3.1:8b

# Or alternative:
ollama pull qwen2.5:7b
```

**Verify model is available:**
```bash
ollama list
# Should show llama3.1:8b or qwen2.5:7b
```

## Step 3: Install Python Dependencies

```bash
pip install pymupdf requests
```

Or add to `requirements.txt`:
```
pymupdf>=1.23.0
requests>=2.31.0
```

## Step 4: Test Single Book

```bash
# Process one book to verify everything works
python -m admin.taxonomy_engine batch1books/Meditations.pdf artifacts/

# Check output
cat artifacts/book_*.json | head -50
```

**Expected output:**
- Artifact JSON file created in `artifacts/`
- Contains: meta, structure, sections, thematic_index, routing_hints
- Confidence score > 0.6

## Step 5: Process All Books

```bash
# Process all PDFs (this will take ~17 hours for 500+ books)
python -m admin.taxonomy_engine batch1books/ artifacts/ --batch

# With resume (skip already processed):
python -m admin.taxonomy_engine batch1books/ artifacts/ --batch --resume
```

**Monitor progress:**
- Each book takes ~2-3 minutes (4 LLM passes)
- 500 books × 2.5 min = ~21 hours
- Can run overnight unattended

## Troubleshooting

### Ollama not responding
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Restart Ollama
pkill ollama
ollama serve
```

### Model not found
```bash
# List available models
ollama list

# Pull model again
ollama pull llama3.1:8b
```

### Out of memory
- Use smaller model: `qwen2.5:7b` instead of `llama3.1:8b`
- Or use Q4 quantized version: `llama3.1:8b-instruct-q4_K_M`

### Slow processing
- Normal: ~30 seconds per LLM call × 4 passes = ~2 min per book
- Can't speed up much without GPU acceleration
- Just let it run overnight

## Output Structure

After processing, `artifacts/` will contain:

```
artifacts/
├── book_abc123.json      ← Canonical artifact (immutable)
├── book_def456.json
├── ...
├── _manifest.json         ← Index of all books + status (to be created)
└── _flagged.json         ← Books needing review (to be created)
```

Each artifact follows the structure defined in manifest.md Section 2.3.

## Next Steps

Once artifacts are created:
1. Validate artifacts meet quality threshold
2. Ingest artifacts into database (separate process)
3. Reader UI consumes artifacts for navigation and rendering
