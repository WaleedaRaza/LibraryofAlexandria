# pipeline2: passage-level parsing and routing

Turns a PDF into anchored logical units (char offsets + page + bbox) and routes questions to them.

Stages: S0 identity check, S1 spans, S2 line roles (furniture/headings/notes), S3 clean text + offset map,
S4 structure and zones (primary/apparatus/front/back/contents), S6 units with voice (author/commentary),
S7 LLM enrichment (questions per unit, optional), S8 FTS5 + vectors, S9 RRF routing with zone weights.

Run from `taxonomy-pipeline/`:

```bash
pip install pymupdf click pyyaml httpx numpy
python -m src.pipeline2.cli ingest --pdf-dir <dir of slug.pdf> --db data/p2.sqlite --catalog ../library/catalog.json
python -m src.pipeline2.cli eval   --db data/p2.sqlite --gold ../eval/gold_v0.py -v
python -m src.pipeline2.cli route  --db data/p2.sqlite "what does Hobbes say life is like without government"

# with local models (set pipeline2.embed/gen provider: ollama in config.yaml)
ollama pull nomic-embed-text && ollama pull qwen2.5:7b-instruct
python -m src.pipeline2.cli enrich --db data/p2.sqlite
python -m src.pipeline2.cli embed  --db data/p2.sqlite
python -m src.pipeline2.cli eval   --db data/p2.sqlite --gold ../eval/gold_v0.py --dense
```

Pilot score (8 books, 119 scored questions, lexical only): recall@10 69/119, recall@1 31/119, MRR 0.357,
against the page-level BM25 baseline of 64/119 and 23/119.
