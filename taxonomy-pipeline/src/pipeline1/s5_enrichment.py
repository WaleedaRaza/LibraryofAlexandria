"""Stage 5: Section Enrichment.

One LLM call per section. Reads the full section text and produces:
- Summary (2-3 sentences)
- Key themes (3-7 tags)
- Notable passages (1-3 with offsets)
- Difficulty rating

Most expensive stage — a book with 20 chapters = 20 LLM calls.
But each call is small context (one section at a time).
"""

from __future__ import annotations
from pathlib import Path

from src.schema import SectionBoundary, SectionEnrichment, NotablePassage
from src.llm import OllamaClient
from src.config import Config
from rich.console import Console

console = Console()


SYSTEM_PROMPT = """You are a literary analyst producing structured metadata about a text section. You respond ONLY in JSON. No explanation, no markdown."""

USER_PROMPT_TEMPLATE = """Analyze this section of a {book_type}.

Section: "{section_title}" ({section_subtype})
Word count: ~{word_count}

---
{section_text}
---

Produce a JSON object with:
{{
  "summary": "2-3 sentences about what this section IS about (its content and significance), not a blow-by-blow",
  "key_themes": ["theme1", "theme2"],
  "notable_passages": [
    {{
      "text": "exact short quote from the text above (max 150 chars)",
      "offset_in_section": 0,
      "significance": "why this passage matters"
    }}
  ],
  "difficulty": "accessible or moderate or challenging"
}}

Rules:
- key_themes: 3-7 tags, lowercase, use underscores for multi-word (e.g. "self_discipline")
- notable_passages: 1-3 passages max. The "text" must be an EXACT quote from the section.
- offset_in_section: approximate character position of the passage within this section text
- difficulty: "accessible" = everyday language, "moderate" = requires some context, "challenging" = dense or technical"""


def run(pdf_path: Path, context: dict, config: Config) -> list[SectionEnrichment]:
    """Enrich each section with summary, themes, passages."""
    cleaning = context["s2_cleaning"]
    boundaries: list[SectionBoundary] = context["s4_boundaries"]
    clean_text = cleaning.clean_text
    structure = context["s3_structure"]

    cfg = config.pipeline1.enrichment

    llm = OllamaClient(
        base_url=config.llm.base_url,
        model=config.llm.model,
        temperature=config.llm.temperature,
        timeout=config.llm.request_timeout,
        max_retries=config.pipeline1.batch.retry_on_failure,
    )

    enrichments = []

    for i, section in enumerate(boundaries):
        section_text = clean_text[section.start_offset:section.end_offset]
        word_count = len(section_text.split())
        reading_time = round(word_count / 200, 1)  # ~200 wpm

        console.print(
            f"  [dim]  Enriching {i + 1}/{len(boundaries)}: "
            f"{section.title} ({word_count} words)[/dim]"
        )

        # For very short sections (< 50 words), skip LLM and use defaults
        if word_count < 50:
            enrichments.append(SectionEnrichment(
                section_id=section.id,
                summary=f"Brief section: {section.title}",
                key_themes=[],
                notable_passages=[],
                difficulty="accessible",
                word_count=word_count,
                reading_time_minutes=reading_time,
            ))
            continue

        # Truncate very long sections for the LLM context window
        # ~8K tokens ≈ 32K chars — most sections won't hit this
        max_chars = 32000
        truncated_text = section_text[:max_chars]
        if len(section_text) > max_chars:
            truncated_text += "\n\n[...section truncated for analysis...]"

        prompt = USER_PROMPT_TEMPLATE.format(
            book_type=structure.book_type,
            section_title=section.title,
            section_subtype=section.subtype,
            word_count=word_count,
            section_text=truncated_text,
        )

        try:
            result = llm.generate_json(prompt, system=SYSTEM_PROMPT)
        except Exception as e:
            console.print(f"  [red]  Failed to enrich {section.id}: {e}[/red]")
            enrichments.append(SectionEnrichment(
                section_id=section.id,
                summary=f"[Enrichment failed: {e}]",
                key_themes=[],
                notable_passages=[],
                difficulty="moderate",
                word_count=word_count,
                reading_time_minutes=reading_time,
            ))
            continue

        # Parse notable passages and convert offsets to absolute
        passages = []
        for p in result.get("notable_passages", [])[:cfg.max_passages_per_section]:
            offset_in_section = p.get("offset_in_section", 0)
            passage_text = p.get("text", "")

            # Try to find the actual offset by searching for the text
            actual_offset = section_text.find(passage_text)
            if actual_offset >= 0:
                abs_start = section.start_offset + actual_offset
                abs_end = abs_start + len(passage_text)
            else:
                # Fallback to the LLM-provided offset
                abs_start = section.start_offset + offset_in_section
                abs_end = abs_start + len(passage_text)

            passages.append(NotablePassage(
                text=passage_text,
                start_offset=abs_start,
                end_offset=abs_end,
                significance=p.get("significance", ""),
            ))

        themes = result.get("key_themes", [])[:cfg.max_themes_per_section]
        # Normalize themes: lowercase, underscore
        themes = [t.lower().strip().replace(" ", "_").replace("-", "_") for t in themes]

        enrichments.append(SectionEnrichment(
            section_id=section.id,
            summary=result.get("summary", ""),
            key_themes=themes,
            notable_passages=passages,
            difficulty=result.get("difficulty", "moderate"),
            word_count=word_count,
            reading_time_minutes=reading_time,
        ))

    console.print(f"  [green]Enriched {len(enrichments)} sections[/green]")
    return enrichments
