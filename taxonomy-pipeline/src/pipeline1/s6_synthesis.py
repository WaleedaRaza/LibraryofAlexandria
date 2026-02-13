"""Stage 6: Book-Level Synthesis.

Single LLM call per book. Reads all section summaries and themes
(NOT full text) and produces:
- Domain classification
- Thematic index (theme → section IDs)
- Routing hints (good_for, not_good_for, pairs_well_with)
- Cross-section references
"""

from __future__ import annotations
from pathlib import Path

from src.schema import (
    SectionBoundary, SectionEnrichment, BookSynthesis,
    RoutingHints, CrossReference,
)
from src.llm import OllamaClient
from src.config import Config
from rich.console import Console

console = Console()


SYSTEM_PROMPT = """You are producing a book-level thematic analysis from per-section summaries. You respond ONLY in JSON. No explanation."""

USER_PROMPT_TEMPLATE = """Here are all sections of this {book_type}, with their summaries and themes:

{sections_summary}

Produce a book-level analysis as JSON:
{{
  "domain": "primary domain (e.g. philosophy, fiction, psychology, history, science, religion, politics, self_improvement, military)",
  "subdomains": ["subdomain1", "subdomain2"],
  "thematic_index": {{
    "theme_name": ["section_id1", "section_id2"],
    "another_theme": ["section_id3"]
  }},
  "routing_hints": {{
    "good_for": [
      "human-readable description of what kind of question or situation this book helps with",
      "another scenario"
    ],
    "not_good_for": [
      "scenario where this book would NOT be helpful"
    ],
    "pairs_well_with": [
      "Book Title -- Author"
    ]
  }},
  "cross_references": [
    {{
      "from_section": "sec_001",
      "to_section": "sec_005",
      "relationship": "elaborates or contrasts or extends",
      "note": "brief explanation of the connection"
    }}
  ]
}}

Rules:
- thematic_index: consolidate themes from all sections. Use broader categories where individual section themes are too specific. Every theme should map to at least 1 section.
- routing_hints.good_for: 3-8 entries. Write as scenarios a real person might face. e.g. "feeling like nothing you do matters" not "existential nihilism".
- routing_hints.not_good_for: 2-5 entries. What this book explicitly can NOT help with.
- routing_hints.pairs_well_with: 1-5 other well-known books that complement this one.
- cross_references: 0-5 connections between sections that share or contrast ideas."""


def _build_sections_summary(
    boundaries: list[SectionBoundary],
    enrichments: list[SectionEnrichment],
) -> str:
    """Compress all section enrichments into a concise format for the LLM."""
    enrichment_map = {e.section_id: e for e in enrichments}

    lines = []
    for section in boundaries:
        enrichment = enrichment_map.get(section.id)
        if enrichment:
            themes_str = ", ".join(enrichment.key_themes) if enrichment.key_themes else "none"
            lines.append(
                f'[{section.id}] "{section.title}" ({section.subtype}):\n'
                f'  Summary: {enrichment.summary}\n'
                f'  Themes: {themes_str}\n'
                f'  Difficulty: {enrichment.difficulty}'
            )
        else:
            lines.append(f'[{section.id}] "{section.title}" ({section.subtype}): [no enrichment]')

    return "\n\n".join(lines)


def run(pdf_path: Path, context: dict, config: Config) -> BookSynthesis:
    """Produce book-level synthesis from section enrichments."""
    boundaries: list[SectionBoundary] = context["s4_boundaries"]
    enrichments: list[SectionEnrichment] = context["s5_enrichment"]
    structure = context["s3_structure"]

    sections_summary = _build_sections_summary(boundaries, enrichments)

    prompt = USER_PROMPT_TEMPLATE.format(
        book_type=structure.book_type,
        sections_summary=sections_summary,
    )

    llm = OllamaClient(
        base_url=config.llm.base_url,
        model=config.llm.model,
        temperature=config.llm.temperature,
        timeout=config.llm.request_timeout,
        max_retries=config.pipeline1.batch.retry_on_failure,
    )

    console.print("  [dim]  Generating book-level synthesis...[/dim]")
    result = llm.generate_json(prompt, system=SYSTEM_PROMPT)

    # Parse routing hints
    raw_hints = result.get("routing_hints", {})
    routing_hints = RoutingHints(
        good_for=raw_hints.get("good_for", []),
        not_good_for=raw_hints.get("not_good_for", []),
        pairs_well_with=raw_hints.get("pairs_well_with", []),
    )

    # Parse cross references
    cross_refs = []
    for cr in result.get("cross_references", []):
        cross_refs.append(CrossReference(
            from_section=cr.get("from_section", ""),
            to_section=cr.get("to_section", ""),
            relationship=cr.get("relationship", "relates"),
            note=cr.get("note", ""),
        ))

    # Validate thematic index references
    valid_ids = {s.id for s in boundaries}
    thematic_index = {}
    for theme, section_ids in result.get("thematic_index", {}).items():
        valid_refs = [sid for sid in section_ids if sid in valid_ids]
        if valid_refs:
            thematic_index[theme.lower().strip()] = valid_refs

    synthesis = BookSynthesis(
        domain=result.get("domain", "unknown"),
        subdomains=result.get("subdomains", []),
        thematic_index=thematic_index,
        routing_hints=routing_hints,
        cross_references=cross_refs,
        model_used=config.llm.model,
    )

    console.print(
        f"  [green]Synthesis complete: {synthesis.domain}, "
        f"{len(thematic_index)} themes, "
        f"{len(routing_hints.good_for)} routing hints[/green]"
    )

    return synthesis
