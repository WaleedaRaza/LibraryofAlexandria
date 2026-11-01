"""Pipeline 2: PDF -> span-anchored logical units -> hybrid index -> routed passages.

Stages (each a function over plain data, persisted by store.py):
  s0_identity   verify the PDF is the book the catalog says it is
  s1_spans      per-page lines with boxes and fonts; overprint removal; OCR flags
  s2_roles      running headers/footers, page numbers, headings, notes, body
  s3_text       clean text with an offset map back to page + bbox
  s4_structure  divisions (outline / headings), zones (primary, apparatus, front, back, contents)
  s6_units      logical units (numbered sections, propositions, commentary, paragraph groups)
  s7_enrich     LLM: per-unit questions + gist (optional, behind config)
  s8_index      SQLite FTS5 (porter, spelling-normalized) + optional embeddings
  s9_route      hybrid retrieval with zone weighting
Voice (S5) is assigned inside s6_units for now (commentary brackets).
"""
