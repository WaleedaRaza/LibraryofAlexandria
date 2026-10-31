# LibXNDR: Book Knowledge Graph and Router

Oct 31, 2026 · Waleed Raza (drafted with Claude). Live, editable version: https://claude.ai/artifact/4rCiRo8LBxzRZ2Ssmrjw8s

## Thesis and where we start

A book that "actually knows" is not a model with the book in its weights. It is an index where every piece of knowledge is pinned to a character span of the real text, and a model that is only allowed to speak from those spans. The graph organizes the spans; retrieval finds them; the model explains them and must cite them. That is what beats a general model trained on what the internet says about books.

Three consequences drive the whole design:

1. **The span is the atom.** Concepts, claims, arguments and skills are annotations over spans, never free-floating text. An LLM output with no span is discarded.
2. **Route to units, not to books.** Retrieve across every unit in the library at once and let "which book, which section" fall out of the ranking. Gating by domain then book then section compounds errors at each gate.
3. **Separate what the author says from what we infer.** "Aristotle defines friendship here" is a fact about the text. "This passage refutes Hobbes" is an interpretation, and the graph must label it as one.

```
Ingest, once per book
  Text + layout -> Divisions -> Units -> Extraction -> Relations
  (pages, OCR)    (canon refs)  (logical,  (claims,     (typed,
                                 typed)     concepts)    evidenced)
                                   |          |            |
                                   v          v            v
  +--------------------------------------------------------------+
  | One Postgres store, every row anchored to a text span        |
  | units with offsets and pages, concept senses, claims, skills,|
  | typed edges, pgvector, full-text                             |
  +--------------------------------------------------------------+
                  |                 |
                  v                 v
Query, per question
  Plan -> Recall -----------> Graph walk -> Rerank -> Route + answer
  (type,  (BM25, dense,        (2 hops max)  (cross-   (cited, checked)
   names)  question index)                    encoder)
```

Ingest writes span-anchored rows into one store; every query reads from that store, and nothing in an answer comes from anywhere else.

### What the repo has today (branch codex/waleeds-library)

| Piece | State | Keep or replace |
| --- | --- | --- |
| taxonomy-pipeline S1 extraction, S2 cleaning | PyMuPDF text, header and page-number stripping, content hash | Keep. Add a char-to-page and word bounding-box map so the PDF reader can highlight a span. |
| S3 structure, S4 boundaries | Book type plus regex/LLM chapter breaks, 4k-token windows on llama3.1:8b | Keep as the division layer. Add canonical reference schemes (Stephanus, Bekker, verse, aphorism numbers). |
| S5 enrichment | Per-section summary, 3-7 themes, up to 3 notable passages | Replace. A chapter summary cannot point at the paragraph that answers a question. |
| S6 synthesis | Book-level thematic index, cross_references with a free-text relationship string | Replace with typed edges in a table, each with evidence spans. |
| app/agents/reading_router.py | Keyword overlap against themes and summaries, only `available_books[:3]` | Replace with hybrid unit retrieval across the whole corpus. |
| library/catalog.json | 544 PDFs, `text_status: pending` on all 544, 313 tagged "General" | Text extraction is step zero. Domain tags are too weak to route on. |
| artifacts/chapter_index.v1.json | 193 books, each one "Full Text" chapter, about 11.9M words | Gives the scale: the full 416 works are roughly 25M words, about 33M tokens. |

No embeddings, vector store or BM25 index exist yet. Supabase Postgres is already in the stack, so pgvector and full-text search are available without a new service.

## Units: chunking by meaning, not by tokens

The retrievable atom is a **unit**: one move the author makes, typically 150 to 600 words. Fixed 512-token chunks cut arguments in half and glue the end of one idea to the start of the next, which is exactly why generic RAG cites the wrong paragraph.

Hierarchy, each level addressed by character offsets into the cleaned text:

- **Work** (Republic) → **Edition** (a specific PDF; 544 editions over 416 works) → **Division** (book, part, chapter from S4) → **Section** (heading-level) → **Unit** → **Sentence**.

Unit types, chosen per book type from S3:

| Unit type | Typical home | What it holds |
| --- | --- | --- |
| argument | treatise, essays | premises and a conclusion, or one step of a longer argument |
| definition | treatise, manual | a term fixed in this author's sense |
| objection / reply | treatise, dialogue | a counter-position and the author's answer |
| skill | manual, self-help, Stoic and religious practice | a procedure: goal, steps, conditions, failure modes |
| exchange | dialogue | a run of speaker turns on one question, with speakers attributed |
| example / case | any | illustration tied to a claim it serves |
| scene | novel, drama | a narrative episode; claims here belong to characters, not the author |
| aphorism / verse | Nietzsche, Marcus Aurelius, scripture, poetry | the natural numbered unit; never merge them |

How boundaries are found, cheapest signal first:

1. **Native numbering wins.** Stephanus pages (Republic 514a), Bekker lines (Nicomachean Ethics 1094a), chapter and verse, Meditations book.section, Ethics propositions. These become `canonical_ref` on the unit, which also lets one highlight map across different editions of the same work.
2. **Paragraphs as candidates**, then **semantic breakpoints**: embed each paragraph and cut where similarity to the neighbors drops (TextTiling-style), merging short paragraphs and splitting ones over about 800 words.
3. **Discourse markers** adjust the cut: "but someone will object", "therefore", "first... second...", speaker changes.
4. **A small model labels** each candidate unit's type and may move a boundary by at most one paragraph. It never rewrites text.

Every unit stores `start_offset`, `end_offset`, page range and word bounding boxes, so a route lands as a highlighted region on the page in the existing PDF reader, not as a chapter title.

## Graph schema

Store the graph in Supabase Postgres: typed node tables, one edge table, pgvector for embeddings, recursive CTEs for walks. At roughly 100k units and a few million edges this fits comfortably, and it keeps reader highlights, notes and the graph in one database. A dedicated graph database adds operations work without adding capability at this size.

### Nodes

| Node | Key fields | Notes |
| --- | --- | --- |
| unit | work_id, edition_id, division_id, type, start/end offset, pages, canonical_ref, text, embedding | The only node that holds text. Everything else points at units. |
| concept_sense | label, author/tradition scope, gloss, defining_unit_ids | "virtue@Aristotle" (arete) is not "virtue@Machiavelli" (virtù). Senses link up to a shared **concept** via `sense_of`. This is what stops cross-book retrieval from matching words instead of ideas. |
| claim | normalized proposition (one sentence), polarity, speaker, stance, unit_id + span | `stance` is asserts, reports, rejects, or entertains. Thrasymachus asserting "justice is the advantage of the stronger" is not Plato asserting it. |
| argument | conclusion claim, ordered premise claims, unit_ids | Arguments often span several units. |
| skill | goal, steps, preconditions, failure modes, unit_ids | For manuals, self-help, Stoic exercises, devotional practice. |
| question | text, unit_id, kind | Questions a unit answers, generated per unit. Indexed for retrieval (see Retrieval). |
| entity / tradition | person, school, work-in-the-world, date range | Needed for chronology and for "responds to". |

### Edges

One table: `edge(id, type, src_kind, src_id, dst_kind, dst_id, scope, basis, evidence_src_span, evidence_dst_span, confidence, extractor, status)`.

| Type | Scope | Meaning |
| --- | --- | --- |
| defines, uses | within work | unit fixes or relies on a concept sense |
| premise_of, concludes | within work | claim role in an argument |
| objects_to, replies_to | within or across | dialectical moves; within a dialogue these are usually explicit |
| prerequisite | within or across | you need concept or unit A to follow B |
| elaborates, example_of | within work | unit expands or illustrates another |
| supports, refutes | across works | claim-level agreement or contradiction |
| extends | across works | builds on and goes beyond |
| responds_to | across works | historically later work addresses earlier one; only valid when chronology allows |
| quotes, cites | across works | detected by string matching, not by a model |
| parallels | across works | same claim or practice in different traditions |

Two fields carry the epistemics:

- `basis` is **explicit** (the text itself says it: "against Hobbes", a quotation, a named opponent) or **inferred** (our model judged it). The UI shows these differently, always.
- `status` is machine, verified, or rejected. Only verified edges, or inferred edges above a measured precision bar, are shown to readers.

**Open question:** the knowledge base built "w warb". If it already has relation types, map them onto this table rather than invent parallel ones.

## Extraction pipeline with local models

Extraction is cheap, deterministic work done first, then small-model labeling per unit, then expensive judgment only on a filtered set of cross-book pairs. Never ask a model to read a whole book and "find relationships"; it will invent them.

1. **Text and layout (no model).** Existing S1/S2, extended with a char-to-page map and word boxes. OCR the scanned PDFs (S1 already flags `is_ocr`). Store cleaned text per edition with its content hash.
2. **Divisions and canonical refs (regex first, model fallback).** Existing S3/S4, plus parsers for Stephanus, Bekker, verse and numbered aphorisms.
3. **Units (embeddings plus a small labeler).** As in the Units section.
4. **Per-unit extraction (one call per unit, 7-14B instruct model, JSON-schema constrained decoding).** Input: the unit, the previous unit's one-line gist, the division title, the book type. Output: unit type, speaker if any, 0-5 claims with stance, concept senses used or defined, skill steps if a skill, 3-5 questions the unit answers, within-work links to nearby units.
5. **Mechanical validation.** Every quoted span must exact-match the source after whitespace normalization. Every claim must be entailed by its unit under a small NLI model. Failures are dropped, not repaired. This is the step that makes local 8B output usable.
6. **Concept consolidation.** Cluster concept senses by embedding plus label, within an author first, then link senses across authors to shared concepts. A larger model reviews merges that cross traditions.
7. **Deterministic cross-book edges.** Quotation and citation detection by n-gram matching across the corpus; named-author mentions ("as Hobbes says") by entity matching. These are `basis: explicit` and high precision.
8. **Inferred cross-book edges.** Candidates: for each claim, its 10 nearest claims in other works by embedding, sharing at least one concept. A cross-encoder NLI model scores entail, contradict or neutral and discards most pairs. A larger model (30-70B class, or a frontier API if you accept that cost) adjudicates the survivors with both spans in view and outputs a typed edge or none. Chronology gates `responds_to`.
9. **Review.** Sample edges by type into the existing review room for accept or reject. Those labels become training and eval data.

Every output row records `extractor` (model, prompt version, run id), so a re-run on a better model is a diff, not a rebuild.

### Rough compute (approximate, not measured)

About 33M tokens of text gives roughly 100k units. Step 4 is about 100k calls, around 120M input and 35M output tokens. On a Mac running an 8B model through Ollama at a few dozen tokens per second, that is on the order of 10 days for the full library, so use the Mac for the pilot only. On one rented data-center GPU with vLLM batching, the same run is closer to a day. Step 8 is bounded by how hard the NLI filter cuts; budget it after measuring on the pilot.

## Retrieval and routing across 400+ books

A question goes to every unit in the library at once; books and sections are ranked as aggregates of their units. 100k units is small for an HNSW index, so there is no reason to pre-filter by domain, and the catalog's domain tags (313 of 544 are "General") are not good enough to filter on anyway.

1. **Plan the query.** A small classifier tags the question: navigational ("where does Plato describe the cave"), definitional, argument ("why does Hobbes think..."), skill ("how do I stop being angry"), comparative ("Hobbes vs Locke on the state of nature"), or out of scope. It also extracts named authors, works and concepts. The plan picks which retrievers and graph walks run.
2. **Recall, three retrievers in parallel, about 200 candidates each.**
    - BM25 over unit text (Postgres full-text to start). Wins on names, quotes, rare terms, canonical refs.
    - Dense over unit embeddings. Wins on paraphrase ("how to handle grief" finding Seneca's consolations).
    - Dense over the generated **questions** per unit, mapped back to their unit. Question-to-question matching closes most of the gap between how readers ask and how authors write.
3. **Fuse** with reciprocal rank fusion. No score calibration needed, robust across retrievers.
4. **Expand along the graph, bounded.** From the top 30 units: add the defining unit of each concept sense they use, the other premises of their argument, the author's reply to an objection, and for comparative questions the sense nodes of each named author plus any `refutes` or `responds_to` edges between them. Cap expansion at 2 hops and about 40 extra units.
5. **Rerank** all candidates with a cross-encoder on (question, unit text plus division title). Keep the top 8-12.
6. **Aggregate for routing.** Book score = best unit score plus a smaller share of the next ones, so one perfect passage beats ten loose mentions. Output: ranked works, and within each, the exact units with page and highlight.

For comparative questions the result is shaped as positions, not a list: each author's units side by side, with the edge between them labeled explicit or inferred. This is the honest version of "models trained on different ideas": each tradition answers in its own words, from its own pages.

The current `ReadingRouter.route` signature can stay; its body becomes a call into this retriever, and the `[:3]` book cap disappears.

## Grounding guarantees

The route itself needs no generation: "read Republic 514a-517a, pages 220-223" is already the answer for most questions. When a written answer is added, these rules hold it to the text:

1. **Closed context.** The answering model sees only the question and the reranked units. No web, no memory of what people say about the book. Its general knowledge may phrase things; it may not supply claims.
2. **Sentence-level citations.** The model outputs each sentence with the unit ids and a short supporting quote. Output is structured, not prose with footnotes.
3. **Mechanical quote check.** Every quote must be an exact substring of its cited unit after normalization. A failed check removes the sentence. This is code, not judgment.
4. **Entailment check.** An NLI model checks each sentence against its cited span. Unsupported sentences are dropped or moved into a clearly marked "interpretation" block.
5. **Speaker check.** A claim cited from a unit with `stance: reports` or from a named character is phrased as theirs ("Thrasymachus argues..."), never as the author's view.
6. **Abstain on weak recall.** If the top reranker score is under a threshold tuned on the eval set, say the library does not address it and show the nearest units instead of answering.

Two practical notes. Show quotes short for in-copyright works, since the public bucket already carries that risk. And the existing Reading Companion already has exact-passage links and prompt-injection separation, so this slots in behind it rather than beside it.

## Fine-tuning: where it helps and where it does not

Train small models that **find and judge** text; do not train a large model to **contain** the books. Fine-tuning a generator on a book's text teaches style and rough associations, not reliable, citable recall. Published comparisons found retrieval beats unsupervised fine-tuning for injecting new knowledge (Ovadia et al., "Fine-Tuning or Retrieval?", 2023), and fine-tuning on unfamiliar facts tends to raise hallucination (Gekhman et al., 2024). A tuned model also cannot tell you which page it got something from, which is the whole product.

The GPT problem, a model that knows what people say about books, is solved by the closed context in Grounding, not by a different set of weights.

| Component | Train it? | Why | Training data | When |
| --- | --- | --- | --- | --- |
| Embedding model | Yes, highest payoff | Off-the-shelf models do not know that "eudaimonia" and "flourishing" are one idea, or that Stoic "indifferents" is a technical term | Generated (question, unit) pairs, reader highlights paired with their passage chats, hard negatives from the same book | After the baseline eval exists |
| Reranker (cross-encoder) | Yes | Biggest single precision gain in most RAG systems; cheap to distill | Labels from a larger model judging (question, unit) relevance, checked against the gold set | Same time |
| Unit-type and boundary classifier | Yes | Runs on every paragraph of 400+ books; an 8B prompt per paragraph is slow and inconsistent | A few thousand units labeled by the big model and spot-checked | After the pilot |
| Relation classifier (supports, refutes, extends, none) | Yes, later | Replaces most big-model adjudication calls in step 8 | Accepted and rejected edges from the review room | After about 1-2k reviewed edges |
| Query planner | Maybe | A small classifier is enough; prompting may do | Logged real questions, labeled | Once traffic exists |
| Per-tradition adapters (LoRA) | Only as a voice, never as knowledge | A Stoic adapter can explain in a Stoic idiom, but will confidently invent Seneca | n/a | Optional, last |
| Generator trained on the books | No | Does not cite, hallucinates more, retrains on every new book | n/a | Never |

Where "different ideas" does belong: concept senses scoped per author and tradition (Graph schema), retrieval restricted to a tradition's works on request, and comparative answers built from each side's own units. That gives a reader "what would an Epicurean say" with page references, which an adapter cannot.

## Evaluation set

Nothing gets tuned, swapped or shipped without a frozen set of questions with gold passages. Start with about 300 questions over a 15-book pilot, grow to about 1,000 over the full library.

| Slice | Share | Example | Gold |
| --- | --- | --- | --- |
| Navigational | 15% | Where does Plato describe the cave? | Republic 514a-517a |
| Definitional | 15% | What does Aristotle mean by friendship of utility? | the defining unit(s) |
| Argument | 20% | Why does Hobbes say life without a state is short? | premises and conclusion units |
| Skill | 15% | How should I respond to an insult, per the Stoics? | Epictetus and Seneca units |
| Comparative | 20% | How do Hobbes and Locke differ on the state of nature? | units from both, plus the expected relation |
| Unanswerable | 15% | Questions the library does not cover | must abstain |

Sources for questions, in order of value:

1. **Waleed and real readers.** 50 questions written from books known well. Then real passage chats and highlights from the reader (with consent), which already pair a question with a passage.
2. **Generated, then filtered.** A model writes questions from a unit; a person keeps the good ones and rewrites them away from the unit's wording, or BM25 will look unrealistically strong.

Metrics:

- **Retrieval:** recall@10 and MRR at unit level, counting a hit when the returned span overlaps the gold span; book-level recall@5 for routing.
- **Answers:** citation precision (cited spans that support their sentence), unsupported-sentence rate, abstention accuracy on the unanswerable slice.
- **Graph:** precision per edge type on 200 sampled edges each; an inferred edge type is shown to readers only above 0.8 precision.

Run it on every pipeline or model change and keep the numbers in the repo, so "better" is a number, not a feeling.

## Phased plan

Each phase ends at a gate measured on the eval set; the graph earns its place only where it beats plain retrieval.

1. **Text for the library.** Run extended S1/S2 on all 544 editions (every one is `text_status: pending` today), with page maps and OCR. Pick a 15-book pilot spanning types: Republic, Nicomachean Ethics, Meditations, Enchiridion, Leviathan, Second Treatise, Wealth of Nations, Beyond Good and Evil, a manual, 1984, a scripture. *Gate:* pilot text with page-accurate offsets.
2. **Units, hybrid retrieval, eval v1 on the pilot.** Units table, BM25 plus dense plus RRF plus reranker, a route view that jumps to the highlighted page. Swap the body of `ReadingRouter.route`. *Gate:* recall@10 and MRR recorded, clearly ahead of the keyword router.
3. **Per-unit extraction and the question index.** Claims, concept senses, skills, questions, within-book edges, with mechanical validation. *Gate:* the question index raises recall@10; claim precision checked on a sample.
4. **Whole library.** Ingest all 416 works on a rented GPU. *Gate:* eval v2 across the full library holds pilot numbers.
5. **Cross-book graph.** Explicit edges first (quotes, citations, named opponents), then inferred edges with review-room sampling. *Gate:* each inferred edge type at 0.8 precision or it stays hidden.
6. **Fine-tunes.** Embedder and reranker on accumulated pairs and labels; unit classifier to replace step-3 prompts. *Gate:* keep a model only if the eval improves.
7. **Grounded answers and comparisons.** Sentence-cited answers with quote and entailment checks, abstention, and the side-by-side positions view. *Gate:* citation precision and abstention accuracy on target before the real model goes live.

### Open questions

- [ ] What is the "warb" knowledge base, and what node and relation types did it use?
- [ ] What hardware will run extraction: which Mac, and is a rented GPU acceptable for the full run?
- [ ] Do in-copyright works get indexed and quoted, or only routed to?
- [ ] Which 15 books are known well enough to write gold questions for?
