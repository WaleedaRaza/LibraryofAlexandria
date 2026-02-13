"""CLI entry point for the taxonomy pipeline.

Usage:
    python -m src.cli process --pdf path/to/book.pdf
    python -m src.cli batch --pdf-dir data/pdfs/
    python -m src.cli batch --resume
    python -m src.cli process --pdf path/to/book.pdf --rerun-from s4_boundaries
    python -m src.cli validate --artifact path/to/artifact.json
    python -m src.cli inspect --artifact path/to/artifact.json
    python -m src.cli check-llm
"""

from __future__ import annotations
import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from src.config import load_config
from src.llm import OllamaClient

console = Console()

VALID_STAGES = [
    "s1_extraction", "s2_cleaning", "s3_structure",
    "s4_boundaries", "s5_enrichment", "s6_synthesis", "s7_validation",
]


@click.group()
@click.option("--config", "config_path", default="config.yaml", help="Path to config.yaml")
@click.pass_context
def cli(ctx, config_path):
    """Taxonomy Pipeline — PDF to Canonical Artifact."""
    ctx.ensure_object(dict)
    ctx.obj["config"] = load_config(config_path)


@cli.command()
@click.option("--pdf", required=True, type=click.Path(exists=True), help="Path to PDF file")
@click.option("--rerun-from", type=click.Choice(VALID_STAGES), help="Re-run from this stage")
@click.pass_context
def process(ctx, pdf, rerun_from):
    """Process a single PDF through Pipeline 1."""
    config = ctx.obj["config"]
    pdf_path = Path(pdf)

    from src.pipeline1.runner import process_book
    artifact = process_book(pdf_path, config, rerun_from=rerun_from)

    console.print(f"\nConfidence: {artifact.quality.confidence}")
    console.print(f"Sections: {len(artifact.sections)}")
    console.print(f"Themes: {len(artifact.synthesis.thematic_index)}")


@cli.command()
@click.option("--pdf-dir", type=click.Path(exists=True), help="Directory of PDFs")
@click.option("--resume", is_flag=True, help="Resume (skip already-processed books)")
@click.pass_context
def batch(ctx, pdf_dir, resume):
    """Process all PDFs in a directory."""
    config = ctx.obj["config"]
    pdf_path = Path(pdf_dir) if pdf_dir else None

    from src.pipeline1.runner import process_batch
    stats = process_batch(config, pdf_dir=pdf_path)


@cli.command()
@click.option("--artifact", required=True, type=click.Path(exists=True), help="Path to artifact JSON")
@click.pass_context
def inspect(ctx, artifact):
    """Inspect an artifact — show structure, quality, sections."""
    path = Path(artifact)
    with open(path) as f:
        data = json.load(f)

    # Header
    console.print(Panel(
        f"[bold]{data.get('book_id', 'unknown')}[/bold]\n"
        f"Generated: {data.get('generated_at', 'unknown')}\n"
        f"Pipeline: v{data.get('pipeline_version', '?')}",
        title="Artifact",
        border_style="blue",
    ))

    # Source
    source = data.get("source", {})
    console.print(f"\nSource: {source.get('filename')} ({source.get('page_count')} pages)")
    console.print(f"OCR: {source.get('is_ocr')} | Quality: {source.get('extraction_quality')}")

    # Text
    text = data.get("text", {})
    console.print(f"\nText: {text.get('word_count', 0):,} words, {text.get('char_count', 0):,} chars")
    console.print(f"Hash: {text.get('content_hash', 'n/a')[:16]}...")

    # Structure
    structure = data.get("structure", {})
    console.print(f"\nType: {structure.get('book_type')} | Pattern: {structure.get('structure_pattern')}")
    console.print(f"Hierarchy: {structure.get('hierarchy_levels')} levels")

    # Sections table
    sections = data.get("sections", [])
    table = Table(title=f"\nSections ({len(sections)})")
    table.add_column("ID", style="cyan")
    table.add_column("Title")
    table.add_column("Type")
    table.add_column("Words", justify="right")
    table.add_column("Themes")

    for s in sections:
        themes = ", ".join(s.get("key_themes", [])[:3])
        if len(s.get("key_themes", [])) > 3:
            themes += "..."
        table.add_row(
            s["id"],
            s["title"][:40],
            s.get("subtype", ""),
            str(s.get("word_count", 0)),
            themes,
        )
    console.print(table)

    # Synthesis
    synthesis = data.get("synthesis", {})
    console.print(f"\nDomain: {synthesis.get('domain')} > {', '.join(synthesis.get('subdomains', []))}")
    console.print(f"Themes in index: {len(synthesis.get('thematic_index', {}))}")

    hints = synthesis.get("routing_hints", {})
    if hints.get("good_for"):
        console.print("\n[bold]Good for:[/bold]")
        for h in hints["good_for"]:
            console.print(f"  • {h}")
    if hints.get("not_good_for"):
        console.print("\n[bold]Not good for:[/bold]")
        for h in hints["not_good_for"]:
            console.print(f"  • {h}")

    # Quality
    quality = data.get("quality", {})
    confidence = quality.get("confidence", 0)
    color = "green" if confidence >= 0.7 else "yellow" if confidence >= 0.5 else "red"
    console.print(f"\n[{color}]Confidence: {confidence}[/{color}]")
    if quality.get("flags"):
        for flag in quality["flags"]:
            console.print(f"  [yellow]⚠ {flag}[/yellow]")


@cli.command("check-llm")
@click.pass_context
def check_llm(ctx):
    """Check if Ollama is running and the model is available."""
    config = ctx.obj["config"]
    llm = OllamaClient(
        base_url=config.llm.base_url,
        model=config.llm.model,
    )

    console.print(f"Checking Ollama at {config.llm.base_url}...")
    console.print(f"Model: {config.llm.model}")

    if llm.is_available():
        console.print("[green]✓ Ollama is running and model is available[/green]")

        # Quick test
        console.print("\nRunning quick test...")
        try:
            result = llm.generate_json(
                'Respond with: {"status": "ok", "message": "hello"}',
                system="You respond only in JSON.",
            )
            console.print(f"[green]✓ LLM responded: {result}[/green]")
        except Exception as e:
            console.print(f"[red]✗ LLM test failed: {e}[/red]")
    else:
        console.print("[red]✗ Ollama is not available or model not found[/red]")
        console.print(f"\nMake sure Ollama is running:")
        console.print(f"  ollama serve")
        console.print(f"  ollama pull {config.llm.model}")
        sys.exit(1)


@cli.command("read-section")
@click.option("--artifact", required=True, type=click.Path(exists=True))
@click.option("--section-id", required=True, help="Section ID (e.g. sec_001)")
@click.pass_context
def read_section(ctx, artifact, section_id):
    """Print the clean text of a specific section."""
    with open(artifact) as f:
        data = json.load(f)

    clean_text = data["text"]["content"]
    sections = data.get("sections", [])

    for s in sections:
        if s["id"] == section_id:
            text = clean_text[s["start_offset"]:s["end_offset"]]
            console.print(Panel(
                f"[bold]{s['title']}[/bold]\n"
                f"Words: {s.get('word_count', 0)} | Difficulty: {s.get('difficulty', '?')}\n"
                f"Summary: {s.get('summary', 'n/a')}",
                title=section_id,
            ))
            console.print(text[:2000])
            if len(text) > 2000:
                console.print(f"\n[dim]...({len(text) - 2000} more chars)[/dim]")
            return

    console.print(f"[red]Section {section_id} not found[/red]")
    console.print(f"Available: {', '.join(s['id'] for s in sections)}")


if __name__ == "__main__":
    cli()
