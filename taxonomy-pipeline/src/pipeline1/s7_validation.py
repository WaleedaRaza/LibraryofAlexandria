"""Stage 7: Validation.

Pure deterministic — no LLM. Checks the assembled artifact for
consistency and produces a confidence score + flags.

Books below the confidence threshold get flagged for human review.
"""

from __future__ import annotations
from pathlib import Path

from src.schema import (
    SectionBoundary, SectionEnrichment, BookSynthesis,
    CleaningResult, ValidationResult,
)
from src.config import Config
from rich.console import Console

console = Console()


def run(pdf_path: Path, context: dict, config: Config) -> ValidationResult:
    """Validate the complete artifact data for consistency."""
    cleaning: CleaningResult = context["s2_cleaning"]
    boundaries: list[SectionBoundary] = context["s4_boundaries"]
    enrichments: list[SectionEnrichment] = context["s5_enrichment"]
    synthesis: BookSynthesis = context["s6_synthesis"]

    cfg = config.pipeline1.validation
    checks = {}
    flags = []

    # ─── Check 1: Section offsets cover full text ───
    if boundaries:
        total_covered = sum(s.end_offset - s.start_offset for s in boundaries)
        gap = cleaning.char_count - total_covered
        checks["offsets_complete"] = abs(gap) <= cfg.max_gap_chars
        if not checks["offsets_complete"]:
            flags.append(f"offset_gap:{gap}_chars")
    else:
        checks["offsets_complete"] = False
        flags.append("no_sections_detected")

    # ─── Check 2: No overlapping sections ───
    sorted_sections = sorted(boundaries, key=lambda s: s.start_offset)
    overlap_found = False
    for i in range(len(sorted_sections) - 1):
        if sorted_sections[i].end_offset > sorted_sections[i + 1].start_offset:
            overlap_found = True
            flags.append(
                f"overlap:{sorted_sections[i].id}->{ sorted_sections[i + 1].id}"
            )
            break
    checks["no_overlaps"] = not overlap_found

    # ─── Check 3: All sections have enrichment ───
    enriched_ids = {e.section_id for e in enrichments}
    section_ids = {s.id for s in boundaries}
    missing = section_ids - enriched_ids
    checks["all_sections_enriched"] = len(missing) == 0
    if missing:
        flags.append(f"missing_enrichment:{missing}")

    # ─── Check 4: All enriched sections have summary + themes ───
    all_have_content = True
    for e in enrichments:
        if not e.summary or e.summary.startswith("[Enrichment failed"):
            all_have_content = False
            flags.append(f"empty_summary:{e.section_id}")
        if not e.key_themes:
            all_have_content = False
            flags.append(f"no_themes:{e.section_id}")
    checks["enrichments_have_content"] = all_have_content

    # ─── Check 5: Thematic index references valid section IDs ───
    all_refs = set()
    for ids in synthesis.thematic_index.values():
        all_refs.update(ids)
    invalid_refs = all_refs - section_ids
    checks["thematic_refs_valid"] = len(invalid_refs) == 0
    if invalid_refs:
        flags.append(f"invalid_theme_refs:{invalid_refs}")

    # ─── Check 6: Word counts plausible ───
    word_counts_ok = all(
        0 < e.word_count < 500000 for e in enrichments if e.word_count > 0
    )
    checks["word_counts_plausible"] = word_counts_ok
    if not word_counts_ok:
        flags.append("implausible_word_counts")

    # ─── Check 7: No empty sections ───
    no_empty = all(s.end_offset - s.start_offset > 0 for s in boundaries)
    checks["no_empty_sections"] = no_empty
    if not no_empty:
        flags.append("empty_sections_found")

    # ─── Check 8: Routing hints exist ───
    has_routing = len(synthesis.routing_hints.good_for) > 0
    checks["has_routing_hints"] = has_routing
    if not has_routing:
        flags.append("no_routing_hints")

    # ─── Check 9: Thematic index is not empty ───
    has_themes = len(synthesis.thematic_index) > 0
    checks["has_thematic_index"] = has_themes
    if not has_themes:
        flags.append("empty_thematic_index")

    # ─── Composite confidence score ───
    total_checks = len(checks)
    passed_count = sum(checks.values())
    confidence = round(passed_count / max(total_checks, 1), 3)

    passed = confidence >= cfg.min_confidence

    # Print summary
    status = "[green]PASSED[/green]" if passed else "[red]FAILED[/red]"
    console.print(f"  Validation: {status} (confidence: {confidence})")
    if flags:
        for flag in flags:
            console.print(f"    [yellow]⚠ {flag}[/yellow]")

    return ValidationResult(
        confidence=confidence,
        flags=flags,
        checks=checks,
        passed=passed,
    )
