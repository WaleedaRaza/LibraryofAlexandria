"""Stage 3: Structural Analysis.

Single LLM call. Reads the first ~4K tokens of clean text
(plus TOC if available) and classifies the book's type and structure.
This shapes all subsequent stages.
"""

from __future__ import annotations
from pathlib import Path

from src.schema import StructureResult
from src.llm import OllamaClient
from src.config import Config


SYSTEM_PROMPT = """You are a book structure analyst. You examine the opening of a book and classify its type and structural pattern. You respond ONLY in JSON. No explanation, no markdown."""

USER_PROMPT_TEMPLATE = """Analyze the opening of this book to classify its structure.

Here is the beginning of the text:
---
{first_text}
---

{toc_section}

Respond with a JSON object containing exactly these fields:
{{
  "book_type": one of "treatise", "novel", "dialogue", "collection", "manual", "poetry", "religious", "essays",
  "structure_pattern": describe the hierarchy e.g. "parts > chapters" or "books > entries" or "sections" or "continuous",
  "hierarchy_levels": integer 1-3 (1=flat chapters, 2=parts>chapters, 3=parts>chapters>sections),
  "has_front_matter": true or false,
  "front_matter_types": list of strings like ["introduction", "preface", "translator_note"],
  "has_back_matter": true or false,
  "back_matter_types": list of strings like ["endnotes", "index", "bibliography", "appendix"],
  "confidence": float 0.0-1.0 indicating your confidence in this classification
}}"""


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English."""
    return len(text) // 4


def _get_first_n_tokens(text: str, n_tokens: int = 4000) -> str:
    """Get approximately the first n_tokens of text."""
    char_limit = n_tokens * 4
    if len(text) <= char_limit:
        return text
    # Cut at a paragraph boundary if possible
    cut_text = text[:char_limit]
    last_para = cut_text.rfind("\n\n")
    if last_para > char_limit * 0.7:
        return cut_text[:last_para]
    return cut_text


def run(pdf_path: Path, context: dict, config: Config) -> StructureResult:
    """Classify book type and structure with a single LLM call."""
    cleaning = context["s2_cleaning"]
    extraction = context["s1_extraction"]

    # Prepare input: first ~4K tokens
    first_text = _get_first_n_tokens(cleaning.clean_text, 4000)

    # Include TOC if available
    toc_section = ""
    if extraction.has_toc and extraction.toc_entries:
        toc_lines = [f"  {e.title} (page {e.page_num})" for e in extraction.toc_entries[:30]]
        toc_section = "The book has an embedded table of contents:\n" + "\n".join(toc_lines)
    else:
        toc_section = "No embedded table of contents was found in this book."

    prompt = USER_PROMPT_TEMPLATE.format(
        first_text=first_text,
        toc_section=toc_section,
    )

    # Call LLM
    llm = OllamaClient(
        base_url=config.llm.base_url,
        model=config.llm.model,
        temperature=config.llm.temperature,
        timeout=config.llm.request_timeout,
        max_retries=config.pipeline1.batch.retry_on_failure,
    )

    result = llm.generate_json(prompt, system=SYSTEM_PROMPT)

    return StructureResult(
        book_type=result.get("book_type", "essays"),
        structure_pattern=result.get("structure_pattern", "chapters"),
        hierarchy_levels=result.get("hierarchy_levels", 1),
        has_front_matter=result.get("has_front_matter", False),
        front_matter_types=result.get("front_matter_types", []),
        has_back_matter=result.get("has_back_matter", False),
        back_matter_types=result.get("back_matter_types", []),
        confidence=result.get("confidence", 0.5),
        model_used=config.llm.model,
    )
