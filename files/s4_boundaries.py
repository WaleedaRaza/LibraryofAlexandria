"""Stage 4: Section Boundary Detection (Hybrid Regex/LLM).

Strategy:
  1. Run regex patterns against clean_text to find structural markers
  2. If regex finds enough sections covering enough text → use regex, skip LLM
  3. If regex finds too few → fall back to LLM sliding window
  4. Post-process: deduplicate, assign IDs, compute end offsets

The regex pass is instant. The LLM pass can take 30-90 min on a local 8B model.
For well-structured books (Metaphysics, Republic, 1984), regex handles it.
For unmarked books (poetry, some essays), LLM is the fallback.
"""

from __future__ import annotations
import re
from pathlib import Path

from src.schema import SectionBoundary, StructureResult
from src.llm import OllamaClient
from src.config import Config
from rich.console import Console

console = Console()


# ─── REGEX PATTERNS ───
# Each pattern: (compiled_regex, level, type, subtype)
# Level 1 = major (Book, Part), Level 2 = chapter/section

REGEX_PATTERNS = [
    # BOOK I, BOOK II, ... BOOK XIV (all caps, Roman numerals)
    (re.compile(r'(?m)^(BOOK\s+[IVXLC]+)'), 1, "body", "book"),
    # Book I, Book II (title case, Roman)
    (re.compile(r'(?m)^(Book\s+[IVXLC]+)'), 1, "body", "book"),
    # Book 1, Book 2 (title case, Arabic)
    (re.compile(r'(?m)^(Book\s+\d+)'), 1, "body", "book"),

    # PART ONE, PART I, Part I, Part One
    (re.compile(r'(?m)^(PART\s+(?:[IVXLC]+|ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|TEN))'), 1, "body", "part"),
    (re.compile(r'(?m)^(Part\s+(?:[IVXLC]+|One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|\d+))'), 1, "body", "part"),

    # CHAPTER 1, Chapter 1, CHAPTER I, Chapter I
    (re.compile(r'(?m)^(CHAPTER\s+(?:\d+|[IVXLC]+))'), 2, "body", "chapter"),
    (re.compile(r'(?m)^(Chapter\s+(?:\d+|[IVXLC]+))'), 2, "body", "chapter"),
    # Ch. 1, Ch. 2 (abbreviated — common in classical texts)
    (re.compile(r'(?m)^(Ch\.\s*\d+)'), 2, "body", "chapter"),

    # ACT I, Act I, ACT 1
    (re.compile(r'(?m)^(ACT\s+(?:[IVXLC]+|\d+))'), 1, "body", "act"),
    (re.compile(r'(?m)^(Act\s+(?:[IVXLC]+|\d+))'), 1, "body", "act"),

    # SCENE 1, Scene 1
    (re.compile(r'(?m)^(SCENE\s+(?:[IVXLC]+|\d+))'), 2, "body", "scene"),
    (re.compile(r'(?m)^(Scene\s+(?:[IVXLC]+|\d+))'), 2, "body", "scene"),

    # Section markers (numbered)
    (re.compile(r'(?m)^(SECTION\s+(?:\d+|[IVXLC]+))'), 2, "body", "section"),
    (re.compile(r'(?m)^(Section\s+(?:\d+|[IVXLC]+))'), 2, "body", "section"),

    # Front matter
    (re.compile(r'(?m)^(INTRODUCTION|Introduction)\s*$'), 0, "front_matter", "introduction"),
    (re.compile(r'(?m)^(PREFACE|Preface)\s*$'), 0, "front_matter", "preface"),
    (re.compile(r'(?m)^(FOREWORD|Foreword)\s*$'), 0, "front_matter", "foreword"),
    (re.compile(r"(?m)^(TRANSLATOR'S NOTE|Translator's Note)\s*$"), 0, "front_matter", "translator_note"),

    # Back matter
    (re.compile(r'(?m)^(ENDNOTES|Endnotes|END NOTES)\s*$'), 0, "back_matter", "endnotes"),
    (re.compile(r'(?m)^(NOTES|Notes)\s*$'), 0, "back_matter", "endnotes"),
    (re.compile(r'(?m)^(BIBLIOGRAPHY|Bibliography)\s*$'), 0, "back_matter", "bibliography"),
    (re.compile(r'(?m)^(INDEX|Index)\s*$'), 0, "back_matter", "index"),
    (re.compile(r'(?m)^(APPENDIX|Appendix)'), 0, "back_matter", "appendix"),
    (re.compile(r'(?m)^(GLOSSARY|Glossary)\s*$'), 0, "back_matter", "glossary"),
]


# ─── REGEX PASS ───

def _regex_find_boundaries(text: str) -> list[dict]:
    """Run all regex patterns against text. Return raw boundary dicts."""
    raw_boundaries = []

    for pattern, level, section_type, subtype in REGEX_PATTERNS:
        for match in pattern.finditer(text):
            raw_boundaries.append({
                "title": match.group(1).strip(),
                "level": level,
                "type": section_type,
                "subtype": subtype,
                "start_offset": match.start(),
            })

    # Sort by offset
    raw_boundaries.sort(key=lambda b: b["start_offset"])
    return raw_boundaries


def _deduplicate_regex(boundaries: list[dict], tolerance: int = 50) -> list[dict]:
    """Remove near-duplicate boundaries from regex.

    Only deduplicates when two boundaries are at the SAME level and close together
    (e.g. 'BOOK I' and 'Book I' both matching). Different levels at nearby offsets
    are parent-child pairs (BOOK I / Ch. 1) and must both be kept.
    """
    if not boundaries:
        return []

    deduped = [boundaries[0]]
    for b in boundaries[1:]:
        prev = deduped[-1]
        offset_close = abs(b["start_offset"] - prev["start_offset"]) < tolerance
        same_level = b["level"] == prev["level"]

        if offset_close and same_level:
            # True duplicate — keep the one with more specific subtype
            if len(b["title"]) > len(prev["title"]):
                deduped[-1] = b
            continue

        deduped.append(b)

    return deduped


def _compute_regex_coverage(boundaries: list[dict], text_length: int) -> float:
    """What fraction of the text is covered by the detected sections?"""
    if not boundaries or text_length == 0:
        return 0.0

    # Compute end offsets (each section ends where next starts, last at text_length)
    total_covered = 0
    for i, b in enumerate(boundaries):
        end = boundaries[i + 1]["start_offset"] if i + 1 < len(boundaries) else text_length
        total_covered += end - b["start_offset"]

    return total_covered / text_length


# ─── LLM FALLBACK ───

LLM_SYSTEM = """You are identifying section boundaries in a book. You look for chapter breaks, part breaks, and other structural divisions. You respond ONLY in JSON. No explanation."""

LLM_PROMPT = """You are identifying section boundaries in a {book_type} that follows the pattern: {structure_pattern}.

Look for {hierarchy_levels} level(s) of structure.
{front_matter_instruction}
{back_matter_instruction}

This chunk starts at character offset {chunk_start} in the full text.

For EACH section boundary, report:
- "title": the section title as written
- "level": 1 for major divisions, 2 for chapters, 3 for sub-sections
- "type": "front_matter", "body", or "back_matter"
- "subtype": "part", "chapter", "section", "entry", "introduction", etc.
- "offset_in_chunk": character position within THIS chunk

Only mark actual structural divisions, NOT paragraph breaks.

---
{chunk_text}
---

Respond: {{"boundaries": [{{"title": "...", "level": 1, "type": "body", "subtype": "chapter", "offset_in_chunk": 0}}]}}
If no boundaries: {{"boundaries": []}}"""


def _chunk_text(text: str, chunk_size_chars: int, overlap_chars: int) -> list[tuple[int, str]]:
    """Split text into overlapping chunks."""
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size_chars, len(text))

        # Cut at paragraph boundary if possible
        if end < len(text):
            search_start = max(end - 500, start)
            last_para = text.rfind("\n\n", search_start, end)
            if last_para > start + chunk_size_chars * 0.7:
                end = last_para + 2

        chunks.append((start, text[start:end]))

        next_start = end - overlap_chars
        if next_start <= start:
            next_start = end
        start = next_start
        if len(text) - start < overlap_chars:
            break

    return chunks


def _llm_find_boundaries(
    text: str, structure: StructureResult, config: Config
) -> list[dict]:
    """Fallback: use LLM sliding window to find boundaries."""
    cfg = config.pipeline1.boundaries
    chunk_size_chars = cfg.chunk_size_tokens * 4
    overlap_chars = cfg.chunk_overlap_tokens * 4

    front_instruction = ""
    if structure.has_front_matter:
        types = ", ".join(structure.front_matter_types) or "introduction, preface"
        front_instruction = f"This book has front matter. Look for: {types}"

    back_instruction = ""
    if structure.has_back_matter:
        types = ", ".join(structure.back_matter_types) or "endnotes, index"
        back_instruction = f"This book has back matter. Look for: {types}"

    llm = OllamaClient(
        base_url=config.llm.base_url,
        model=config.llm.model,
        temperature=config.llm.temperature,
        timeout=config.llm.request_timeout,
        max_retries=config.pipeline1.batch.retry_on_failure,
    )

    chunks = _chunk_text(text, chunk_size_chars, overlap_chars)
    console.print(f"  [dim]LLM fallback: {len(chunks)} chunks[/dim]")

    all_boundaries = []

    for i, (chunk_start, chunk_text) in enumerate(chunks):
        console.print(
            f"  [dim]  Chunk {i + 1}/{len(chunks)} "
            f"(offset {chunk_start:,}, {len(chunk_text):,} chars)[/dim]"
        )

        prompt = LLM_PROMPT.format(
            book_type=structure.book_type,
            structure_pattern=structure.structure_pattern,
            hierarchy_levels=structure.hierarchy_levels,
            front_matter_instruction=front_instruction,
            back_matter_instruction=back_instruction,
            chunk_start=chunk_start,
            chunk_text=chunk_text,
        )

        try:
            result = llm.generate_json(prompt, system=LLM_SYSTEM)
        except Exception as e:
            console.print(f"  [red]  Chunk {i + 1} failed: {e}[/red]")
            continue

        for b in result.get("boundaries", []):
            offset_in_chunk = b.get("offset_in_chunk", 0)
            all_boundaries.append({
                "title": b.get("title", "Untitled"),
                "level": b.get("level", 2),
                "type": b.get("type", "body"),
                "subtype": b.get("subtype", "chapter"),
                "start_offset": chunk_start + offset_in_chunk,
            })

    return all_boundaries


def _deduplicate_llm(boundaries: list[dict], tolerance: int = 200) -> list[dict]:
    """Remove duplicate boundaries from LLM overlap regions."""
    if not boundaries:
        return []

    sorted_bounds = sorted(boundaries, key=lambda b: b["start_offset"])
    deduped = [sorted_bounds[0]]

    for b in sorted_bounds[1:]:
        prev = deduped[-1]
        offset_close = abs(b["start_offset"] - prev["start_offset"]) < tolerance
        title_match = (
            b["title"].lower().strip() == prev["title"].lower().strip()
            or b["subtype"] == prev["subtype"]
        )
        if offset_close and title_match:
            if b["start_offset"] < prev["start_offset"]:
                deduped[-1] = b
            continue
        deduped.append(b)

    return deduped


# ─── POST-PROCESSING ───

def _assign_ids(boundaries: list[dict]) -> list[dict]:
    """Assign section IDs: fm_001, sec_001, bm_001."""
    fm_count = 0
    sec_count = 0
    bm_count = 0

    for b in boundaries:
        if b["type"] == "front_matter":
            fm_count += 1
            b["id"] = f"fm_{fm_count:03d}"
        elif b["type"] == "back_matter":
            bm_count += 1
            b["id"] = f"bm_{bm_count:03d}"
        else:
            sec_count += 1
            b["id"] = f"sec_{sec_count:03d}"

    return boundaries


def _compute_end_offsets(boundaries: list[dict], total_length: int) -> list[dict]:
    """Each section ends where the next begins. Last ends at total_length."""
    for i in range(len(boundaries) - 1):
        boundaries[i]["end_offset"] = boundaries[i + 1]["start_offset"]
    if boundaries:
        boundaries[-1]["end_offset"] = total_length
    return boundaries


def _handle_front_matter(
    boundaries: list[dict], text_length: int
) -> list[dict]:
    """If the first boundary doesn't start at offset 0, add front matter section."""
    if not boundaries:
        return boundaries

    first_offset = boundaries[0]["start_offset"]
    if first_offset > 200:
        # There's substantial text before the first detected section
        fm = {
            "title": "Front Matter",
            "level": 0,
            "type": "front_matter",
            "subtype": "front_matter",
            "start_offset": 0,
        }
        boundaries.insert(0, fm)

    return boundaries


# ─── MAIN ENTRY POINT ───

def run(pdf_path: Path, context: dict, config: Config) -> list[SectionBoundary]:
    """Detect section boundaries. Regex first, LLM fallback.

    Flow:
    1. Run regex patterns
    2. Check coverage: enough sections + enough text covered?
    3. If yes → use regex results (instant)
    4. If no → fall back to LLM sliding window (slow)
    5. Post-process: front matter, IDs, end offsets
    """
    cleaning = context["s2_cleaning"]
    structure = context["s3_structure"]
    clean_text = cleaning.clean_text
    text_length = cleaning.char_count

    cfg = config.pipeline1.boundaries

    # ─── Step 1: Regex pass ───
    console.print("  [dim]Running regex boundary detection...[/dim]")
    regex_boundaries = _regex_find_boundaries(clean_text)
    regex_boundaries = _deduplicate_regex(regex_boundaries)
    coverage = _compute_regex_coverage(regex_boundaries, text_length)

    console.print(
        f"  [dim]Regex found {len(regex_boundaries)} boundaries, "
        f"{coverage:.0%} text coverage[/dim]"
    )

    # ─── Step 2: Decide regex vs LLM ───
    use_regex = (
        len(regex_boundaries) >= cfg.regex_min_sections
        and coverage >= cfg.regex_min_coverage
    )

    if use_regex:
        console.print(
            f"  [green]Regex sufficient "
            f"({len(regex_boundaries)} sections, {coverage:.0%} coverage) "
            f"— skipping LLM[/green]"
        )
        boundaries = regex_boundaries
    else:
        console.print(
            f"  [yellow]Regex insufficient "
            f"({len(regex_boundaries)} sections, {coverage:.0%} coverage) "
            f"— falling back to LLM[/yellow]"
        )
        llm_boundaries = _llm_find_boundaries(clean_text, structure, config)
        llm_boundaries = _deduplicate_llm(llm_boundaries)

        # Merge: use regex boundaries as anchors, add LLM discoveries
        if regex_boundaries and llm_boundaries:
            # Combine and deduplicate
            combined = regex_boundaries + llm_boundaries
            combined.sort(key=lambda b: b["start_offset"])
            boundaries = _deduplicate_llm(combined)
        elif llm_boundaries:
            boundaries = llm_boundaries
        elif regex_boundaries:
            boundaries = regex_boundaries
        else:
            # Nothing found at all — single section fallback
            console.print("  [yellow]No boundaries found — single section fallback[/yellow]")
            boundaries = [{
                "title": "Full Text",
                "level": 1,
                "type": "body",
                "subtype": "chapter",
                "start_offset": 0,
            }]

    # ─── Step 3: Post-process ───
    boundaries = _handle_front_matter(boundaries, text_length)
    boundaries = _assign_ids(boundaries)
    boundaries = _compute_end_offsets(boundaries, text_length)

    # Log results
    for b in boundaries:
        size = b.get("end_offset", 0) - b["start_offset"]
        console.print(
            f"    {b['id']:>8}  {b['title']:<40} "
            f"{b['start_offset']:>8}-{b.get('end_offset', '?'):>8} "
            f"({size:,} chars)"
        )

    console.print(f"  [green]Detected {len(boundaries)} sections[/green]")

    return [
        SectionBoundary(
            id=b["id"],
            level=b["level"],
            type=b["type"],
            subtype=b["subtype"],
            title=b["title"],
            start_offset=b["start_offset"],
            end_offset=b.get("end_offset", 0),
        )
        for b in boundaries
    ]
