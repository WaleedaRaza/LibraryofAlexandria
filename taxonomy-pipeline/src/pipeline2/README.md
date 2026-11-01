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

# local models (config.yaml pipeline2 defaults): Ollama plus a /rerank server on :8088
ollama pull qwen3-embedding:4b && ollama pull gemma4:12b
python -m src.pipeline2.cli enrich --db data/p2.sqlite      # skips units with invalid model JSON; rerun to retry
python -m src.pipeline2.cli embed  --db data/p2.sqlite
python -m src.pipeline2.cli eval   --db data/p2.sqlite --gold ../eval/gold_v0.py            # dense + rerank
python -m src.pipeline2.cli eval   --db data/p2.sqlite --gold ../eval/gold_v0.py --no-rerank
# without any models: add --no-dense --no-rerank, or set the providers to none
```

Pilot score (8 books, 119 scored questions, lexical only): recall@10 69/119, recall@1 31/119, MRR 0.357,
against the page-level BM25 baseline of 64/119 and 23/119. With qwen3-embedding:4b dense vectors and
generated questions: 86/119 and 50/119 (before the rerank stage).

## Explorer (local)

```bash
python -m src.pipeline2.explore --db data/p2.sqlite          # http://127.0.0.1:8765
```

Shelf (books, zones, parsing warnings), book view (division barcodes, text by unit, commentary voices,
generated questions, nearest passages in other books), atlas (all units in 2D from the configured embedder's
unit vectors; computed once into `unit_xy`, `--reproject` to redo), ask (S9 routing with per-retriever ranks and
gold-anchor checks; dense and rerank are used when their servers answer), gold set browser. Needs numpy and
the pipeline's own dependencies; no CDN. Writes only `unit_xy` and `gold_candidate` ("save as gold").
Design: "LibXNDR: Reading Lenses, Explorer and the Whole App" (https://claude.ai/artifact/6bTDhrV9HxA7HcDqwmuA6q).
