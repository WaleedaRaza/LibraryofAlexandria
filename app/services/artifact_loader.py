"""
Alexandria - Artifact Loader

THE source of truth for book content in the new architecture.
Loads canonical artifacts from taxonomy-pipeline JSON files.
No database needed for book text — it's all on disk.

Artifacts live at: taxonomy-pipeline/data/artifacts/{book_id}.json

Each artifact contains:
- text.content  (full book text)
- sections[]    (id, title, start_offset, end_offset, summary, key_themes, ...)
- synthesis     (domain, subdomains, thematic_index, routing_hints)
- quality       (confidence, flags)
"""

import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from functools import lru_cache


# =============================================================================
# ARTIFACT DIRECTORY
# =============================================================================

def _artifact_dir() -> Path:
    return Path(__file__).parent.parent.parent / "taxonomy-pipeline" / "data" / "artifacts"


# =============================================================================
# LOADING (cached — artifacts don't change at runtime)
# =============================================================================

@lru_cache(maxsize=32)
def _load_artifact(book_id: str) -> Optional[Dict[str, Any]]:
    """Load and cache artifact JSON. Returns None if not found."""
    path = _artifact_dir() / f"{book_id}.json"
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


# =============================================================================
# DISCOVERY — what books exist?
# =============================================================================

def get_available_books() -> List[str]:
    """List all book_ids that have artifacts on disk."""
    d = _artifact_dir()
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.json"))


def get_all_books() -> List[Dict[str, Any]]:
    """Get metadata for all available artifact books."""
    return [b for bid in get_available_books() if (b := get_book(bid)) is not None]


def get_books_by_domain(domain: str) -> List[Dict[str, Any]]:
    """Get all books matching a domain."""
    result = []
    for bid in get_available_books():
        art = _load_artifact(bid)
        if not art:
            continue
        synth = art.get("synthesis", {})
        art_domain = synth.get("domain", "")
        if art_domain.lower() == domain.lower():
            book = get_book(bid)
            if book:
                result.append(book)
    return result


# =============================================================================
# BOOK METADATA
# =============================================================================

def get_book(book_id: str) -> Optional[Dict[str, Any]]:
    """
    Get book dict from artifact (id, title, author, domain, subdomain).
    Derives title/author from book_id and synthesis data.
    """
    art = _load_artifact(book_id)
    if not art:
        return None

    synth = art.get("synthesis", {})
    source = art.get("source", {})

    # Derive title and author from book_id or source filename
    title, author = _derive_title_author(book_id, source.get("filename", ""))

    return {
        "id": book_id,
        "title": title,
        "author": author,
        "domain": synth.get("domain", "Philosophy"),
        "subdomain": (synth.get("subdomains") or [""])[0],
        "is_public": 1,
    }


def _derive_title_author(book_id: str, filename: str) -> tuple:
    """
    Best-effort title/author from book_id.
    book_id format: title_author (e.g. metaphysics_aristotle)
    """
    # Known overrides
    KNOWN = {
        "metaphysics_aristotle": ("Metaphysics", "Aristotle"),
    }
    if book_id in KNOWN:
        return KNOWN[book_id]

    # Fallback: parse from book_id
    parts = book_id.replace("_", " ").title().rsplit(" ", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return parts[0], "Unknown"


# =============================================================================
# SECTIONS (the new "chapters")
# =============================================================================

def get_sections(book_id: str) -> List[Dict[str, Any]]:
    """Get all sections for a book, with metadata."""
    art = _load_artifact(book_id)
    if not art:
        return []
    return art.get("sections", [])


def get_sections_as_chapters(book_id: str) -> List[Dict[str, Any]]:
    """
    Sections formatted as chapter dicts for compatibility with
    the Reading Router and reader template.
    """
    sections = get_sections(book_id)
    chapters = []
    for i, s in enumerate(sections):
        chapters.append({
            "id": s.get("id", f"sec_{i+1:03d}"),
            "book_id": book_id,
            "number": i + 1,
            "title": s.get("title", f"Section {i + 1}"),
            "start_offset": s.get("start_offset", 0),
            "end_offset": s.get("end_offset", 0),
            # Enrichment data for smarter routing
            "summary": s.get("summary", ""),
            "key_themes": s.get("key_themes", []),
        })
    return chapters


def get_section(book_id: str, section_id: str) -> Optional[Dict[str, Any]]:
    """Get a single section dict by id."""
    for s in get_sections(book_id):
        if s.get("id") == section_id:
            return s
    return None


def get_section_by_number(book_id: str, number: int) -> Optional[Dict[str, Any]]:
    """Get section as chapter dict by 1-based number."""
    chapters = get_sections_as_chapters(book_id)
    return next((c for c in chapters if c["number"] == number), None)


# =============================================================================
# TEXT
# =============================================================================

def get_full_text(book_id: str) -> Optional[str]:
    """Get the full text of a book."""
    art = _load_artifact(book_id)
    if not art:
        return None
    return art.get("text", {}).get("content")


def get_section_text(book_id: str, section_id: str) -> Optional[str]:
    """Get text for a specific section."""
    art = _load_artifact(book_id)
    if not art:
        return None

    content = art.get("text", {}).get("content", "")
    if not content:
        return None

    for s in art.get("sections", []):
        if s.get("id") == section_id:
            start = s.get("start_offset", 0)
            end = s.get("end_offset", len(content))
            return content[start:end]
    return None


# =============================================================================
# SYNTHESIS — routing hints, thematic index
# =============================================================================

def get_routing_hints(book_id: str) -> Dict[str, Any]:
    """Get routing hints (good_for, not_good_for, pairs_well_with)."""
    art = _load_artifact(book_id)
    if not art:
        return {}
    return art.get("synthesis", {}).get("routing_hints", {})


def get_thematic_index(book_id: str) -> Dict[str, List[str]]:
    """Get theme → [section_ids] mapping."""
    art = _load_artifact(book_id)
    if not art:
        return {}
    return art.get("synthesis", {}).get("thematic_index", {})


# =============================================================================
# ROUTING SUPPORT — enriched data for intelligent section selection
# =============================================================================

def get_routable_sections(book_id: str) -> List[Dict[str, Any]]:
    """
    Sections filtered and enriched for routing decisions.
    Strips front/back matter, tiny stubs, and sections with no content signal.
    Returns only sections a human would actually want to read.
    """
    chapters = get_sections_as_chapters(book_id)
    routable = []
    for ch in chapters:
        sid = ch["id"]
        # Skip front/back matter
        if sid.startswith("fm_") or sid.startswith("bm_"):
            continue
        # Skip tiny sections (headers, dividers)
        size = ch["end_offset"] - ch["start_offset"]
        if size < 200:
            continue
        # Skip sections with no routing signal
        if not ch["key_themes"] and not ch["summary"]:
            continue
        routable.append(ch)
    return routable


def build_theme_to_sections(book_id: str) -> Dict[str, List[str]]:
    """
    Build a comprehensive theme → [section_ids] mapping.
    Merges the artifact's thematic_index with per-section key_themes.
    This is what the router uses to match questions to sections.
    """
    mapping: Dict[str, List[str]] = {}

    # Start with the synthesis thematic_index
    ti = get_thematic_index(book_id)
    for theme, sids in ti.items():
        normalized = theme.lower().replace("_", " ")
        mapping[normalized] = list(sids)

    # Enrich with per-section key_themes (much denser coverage)
    for s in get_sections(book_id):
        sid = s.get("id", "")
        for theme in s.get("key_themes", []):
            normalized = theme.lower().replace("_", " ")
            if normalized not in mapping:
                mapping[normalized] = []
            if sid not in mapping[normalized]:
                mapping[normalized].append(sid)

    return mapping


# =============================================================================
# CONVENIENCE
# =============================================================================

def is_artifact_book(book_id: str) -> bool:
    """Check if a book exists as an artifact."""
    return _load_artifact(book_id) is not None
