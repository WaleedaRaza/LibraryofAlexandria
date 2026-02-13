"""Pipeline 1 Runner.

Orchestrates all 7 stages for a single book or batch of books.
Supports checkpointing (resume after crash) and selective re-runs.
Logs elapsed time per stage.
"""

from __future__ import annotations
import json
import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from src.config import Config
from src.schema import (
    CanonicalArtifact, SourceInfo, TextInfo, QualityInfo,
    Section, NotablePassage,
    ExtractionResult, CleaningResult, StructureResult,
    SectionBoundary, SectionEnrichment, BookSynthesis, ValidationResult,
)
from src.pipeline1 import (
    s1_extraction,
    s2_cleaning,
    s3_structure,
    s4_boundaries,
    s5_enrichment,
    s6_synthesis,
    s7_validation,
)

console = Console()

# Stage registry — order matters
STAGES = [
    ("s1_extraction", s1_extraction.run),
    ("s2_cleaning", s2_cleaning.run),
    ("s3_structure", s3_structure.run),
    ("s4_boundaries", s4_boundaries.run),
    ("s5_enrichment", s5_enrichment.run),
    ("s6_synthesis", s6_synthesis.run),
    ("s7_validation", s7_validation.run),
]

# Pydantic model for each stage result (for deserialization)
STAGE_MODELS = {
    "s1_extraction": ExtractionResult,
    "s2_cleaning": CleaningResult,
    "s3_structure": StructureResult,
    "s4_boundaries": None,  # list[SectionBoundary]
    "s5_enrichment": None,  # list[SectionEnrichment]
    "s6_synthesis": BookSynthesis,
    "s7_validation": ValidationResult,
}


def derive_book_id(pdf_path: Path | str) -> str:
    """Derive a stable book ID from the PDF filename."""
    pdf_path = Path(pdf_path)
    stem = pdf_path.stem
    book_id = stem.lower()
    book_id = book_id.replace(" ", "_").replace("-", "_")
    while "__" in book_id:
        book_id = book_id.replace("__", "_")
    book_id = book_id.strip("_")
    return book_id


def _save_checkpoint(checkpoint_file: Path, data) -> None:
    """Save a stage result to disk."""
    checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(data, "model_dump"):
        serialized = data.model_dump()
    elif isinstance(data, list):
        serialized = [
            item.model_dump() if hasattr(item, "model_dump") else item
            for item in data
        ]
    else:
        serialized = data
    with open(checkpoint_file, "w") as f:
        json.dump(serialized, f, indent=2, default=str)


def _load_checkpoint(checkpoint_file: Path, stage_name: str):
    """Load a stage result from disk."""
    with open(checkpoint_file) as f:
        data = json.load(f)

    if stage_name == "s4_boundaries":
        return [SectionBoundary(**item) for item in data]
    elif stage_name == "s5_enrichment":
        return [SectionEnrichment(**item) for item in data]
    elif stage_name in STAGE_MODELS and STAGE_MODELS[stage_name]:
        return STAGE_MODELS[stage_name](**data)
    return data


def _clear_checkpoints_from(checkpoint_dir: Path, from_stage: str) -> None:
    """Delete checkpoints for a stage and all subsequent stages."""
    found = False
    for stage_name, _ in STAGES:
        if stage_name == from_stage:
            found = True
        if found:
            cp = checkpoint_dir / f"{stage_name}.json"
            if cp.exists():
                cp.unlink()
                console.print(f"  [dim]Cleared checkpoint: {stage_name}[/dim]")


def _file_hash(path: Path) -> str:
    """SHA-256 of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _format_elapsed(seconds: float) -> str:
    """Format seconds into human-readable string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    if minutes < 60:
        return f"{minutes}m {secs:.0f}s"
    hours = int(minutes // 60)
    mins = minutes % 60
    return f"{hours}h {mins}m"


def _assemble_artifact(
    book_id: str, pdf_path: Path, context: dict
) -> CanonicalArtifact:
    """Merge all stage results into a single CanonicalArtifact."""
    extraction: ExtractionResult = context["s1_extraction"]
    cleaning: CleaningResult = context["s2_cleaning"]
    structure: StructureResult = context["s3_structure"]
    boundaries: list[SectionBoundary] = context["s4_boundaries"]
    enrichments: list[SectionEnrichment] = context["s5_enrichment"]
    synthesis: BookSynthesis = context["s6_synthesis"]
    validation: ValidationResult = context["s7_validation"]

    # Merge boundaries + enrichments into Section objects
    enrichment_map = {e.section_id: e for e in enrichments}
    sections = []
    for b in boundaries:
        e = enrichment_map.get(b.id)
        sections.append(Section(
            id=b.id,
            level=b.level,
            type=b.type,
            subtype=b.subtype,
            title=b.title,
            start_offset=b.start_offset,
            end_offset=b.end_offset,
            word_count=e.word_count if e else 0,
            reading_time_minutes=e.reading_time_minutes if e else 0.0,
            summary=e.summary if e else "",
            key_themes=e.key_themes if e else [],
            notable_passages=e.notable_passages if e else [],
            difficulty=e.difficulty if e else "moderate",
        ))

    return CanonicalArtifact(
        book_id=book_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        source=SourceInfo(
            filename=pdf_path.name,
            file_hash=_file_hash(pdf_path),
            page_count=extraction.page_count,
            is_ocr=extraction.is_ocr,
            extraction_quality=extraction.extraction_quality,
        ),
        text=TextInfo(
            content=cleaning.clean_text,
            char_count=cleaning.char_count,
            word_count=cleaning.word_count,
            content_hash=cleaning.content_hash,
            cleaning_log=cleaning.cleaning_log,
        ),
        structure=structure,
        sections=sections,
        synthesis=synthesis,
        quality=QualityInfo(
            confidence=validation.confidence,
            flags=validation.flags,
            validation_checks=validation.checks,
        ),
    )


def process_book(
    pdf_path: Path,
    config: Config,
    rerun_from: str | None = None,
) -> CanonicalArtifact:
    """Process a single book through all Pipeline 1 stages."""
    book_id = derive_book_id(pdf_path)
    checkpoint_dir = Path(config.pipeline1.checkpoint_dir) / book_id

    console.print(Panel(
        f"[bold]{pdf_path.name}[/bold]\n"
        f"Book ID: {book_id}",
        title="Processing Book",
        border_style="blue",
    ))

    # Handle rerun
    if rerun_from:
        _clear_checkpoints_from(checkpoint_dir, rerun_from)

    context = {}
    stage_times = {}
    total_start = time.time()

    for stage_name, stage_fn in STAGES:
        checkpoint_file = checkpoint_dir / f"{stage_name}.json"

        if checkpoint_file.exists():
            console.print(f"  [dim]⏭ {stage_name} (cached)[/dim]")
            context[stage_name] = _load_checkpoint(checkpoint_file, stage_name)
            continue

        console.print(f"  [cyan]▶ {stage_name}[/cyan]")
        stage_start = time.time()

        try:
            result = stage_fn(pdf_path=pdf_path, context=context, config=config)
        except Exception as e:
            elapsed = time.time() - stage_start
            console.print(
                f"  [red]✗ {stage_name} failed after "
                f"{_format_elapsed(elapsed)}: {e}[/red]"
            )
            raise

        elapsed = time.time() - stage_start
        stage_times[stage_name] = elapsed

        context[stage_name] = result
        _save_checkpoint(checkpoint_file, result)
        console.print(
            f"  [green]✓ {stage_name}[/green] [dim]({_format_elapsed(elapsed)})[/dim]"
        )

    total_elapsed = time.time() - total_start

    # Assemble final artifact
    artifact = _assemble_artifact(book_id, pdf_path, context)

    # Save artifact
    artifact_dir = Path(config.pipeline1.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / f"{book_id}.json"

    with open(artifact_path, "w") as f:
        json.dump(artifact.model_dump(), f, indent=2, default=str)

    # Flag if below confidence threshold
    if not context["s7_validation"].passed:
        flagged_dir = Path(config.pipeline1.flagged_dir)
        flagged_dir.mkdir(parents=True, exist_ok=True)
        flagged_link = flagged_dir / f"{book_id}.json"
        if not flagged_link.exists():
            flagged_link.symlink_to(artifact_path.resolve())
        console.print(
            f"  [yellow]⚠ Flagged for review "
            f"(confidence: {artifact.quality.confidence})[/yellow]"
        )

    # Summary
    console.print(Panel(
        f"Sections: {len(artifact.sections)}\n"
        f"Themes: {len(artifact.synthesis.thematic_index)}\n"
        f"Confidence: {artifact.quality.confidence}\n"
        f"Total time: {_format_elapsed(total_elapsed)}\n"
        + (
            "\n".join(
                f"  {name}: {_format_elapsed(t)}"
                for name, t in stage_times.items()
            )
            if stage_times else "  (all cached)"
        ),
        title=f"✓ {book_id}",
        border_style="green",
    ))

    return artifact


def process_batch(config: Config, pdf_dir: Path | None = None) -> dict:
    """Process all PDFs in a directory. Returns summary stats."""
    pdf_dir = pdf_dir or Path(config.pipeline1.pdf_dir)
    artifact_dir = Path(config.pipeline1.artifact_dir)

    pdfs = sorted(pdf_dir.glob("*.pdf"))
    total = len(pdfs)

    console.print(Panel(
        f"Found {total} PDFs in {pdf_dir}",
        title="Batch Processing",
        border_style="blue",
    ))

    stats = {
        "total": total, "completed": 0, "skipped": 0,
        "failed": 0, "flagged": 0,
    }
    batch_start = time.time()

    for i, pdf_path in enumerate(pdfs):
        book_id = derive_book_id(pdf_path)
        artifact_path = artifact_dir / f"{book_id}.json"

        console.print(f"\n[bold]({i + 1}/{total})[/bold]")

        if artifact_path.exists():
            console.print(f"  [dim]Skipping {pdf_path.name} (artifact exists)[/dim]")
            stats["skipped"] += 1
            continue

        try:
            artifact = process_book(pdf_path, config)
            stats["completed"] += 1
            if artifact.quality.confidence < config.pipeline1.validation.min_confidence:
                stats["flagged"] += 1
        except Exception as e:
            console.print(f"  [red]✗ FAILED: {pdf_path.name}: {e}[/red]")
            stats["failed"] += 1
            continue

    batch_elapsed = time.time() - batch_start

    console.print(Panel(
        f"Completed: {stats['completed']}\n"
        f"Skipped: {stats['skipped']}\n"
        f"Failed: {stats['failed']}\n"
        f"Flagged: {stats['flagged']}\n"
        f"Total time: {_format_elapsed(batch_elapsed)}",
        title="Batch Complete",
        border_style="green",
    ))

    return stats
