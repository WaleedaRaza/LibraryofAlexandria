"""
Alexandria Library - Artifact Builder
Admin-only script to generate book_index and chapter_index from database.

Usage:
    python -m admin.build_artifacts
    
This reads the current DB state and outputs:
- artifacts/book_index.v{N}.json
- artifacts/chapter_index.v{N}.json

Version is auto-incremented on each run.
"""

import json
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any


# Paths
BASE_DIR = Path(__file__).parent.parent
ARTIFACTS_DIR = BASE_DIR / "artifacts"
DB_PATH = BASE_DIR / "data" / "alexandria.db"
TAXONOMY_PATH = ARTIFACTS_DIR / "taxonomy.v1.json"


# Domain/subdomain mappings (based on book content)
# In production, this could be stored in DB or derived from book.domain field
BOOK_TAXONOMY_MAPPINGS = {
    "book_d9d95145167f": {  # Meditations
        "title": "Meditations",
        "author": "Marcus Aurelius",
        "domain_ids": ["philosophy"],
        "subdomain_ids": ["stoicism"]
    },
    "book_e500fb226315": {  # The Art of War
        "title": "The Art of War",
        "author": "Sun Tzu",
        "domain_ids": ["strategy"],
        "subdomain_ids": ["military"]
    },
    "book_062ae004ce4a": {  # The 48 Laws of Power
        "title": "The 48 Laws of Power",
        "author": "Robert Greene",
        "domain_ids": ["strategy", "psychology"],
        "subdomain_ids": ["power", "social"]
    },
    "book_5e3b6dc26640": {  # Thinking in Systems
        "title": "Thinking in Systems",
        "author": "Donella H. Meadows",
        "domain_ids": ["technology", "economics"],
        "subdomain_ids": ["systems"]
    },
    "book_aaf47b37c1b4": {  # Miracle of Mindfulness
        "title": "The Miracle of Mindfulness",
        "author": "Thich Nhat Hanh",
        "domain_ids": ["psychology", "philosophy"],
        "subdomain_ids": ["mindfulness"]
    },
}


def get_current_version() -> int:
    """Find the highest existing version number in artifacts dir."""
    if not ARTIFACTS_DIR.exists():
        return 0
    
    versions = []
    for path in ARTIFACTS_DIR.glob("book_index.v*.json"):
        try:
            version_str = path.stem.split(".v")[1]
            versions.append(int(version_str))
        except (IndexError, ValueError):
            continue
    
    return max(versions) if versions else 0


def load_taxonomy() -> Dict[str, Any]:
    """Load the taxonomy artifact."""
    if not TAXONOMY_PATH.exists():
        raise FileNotFoundError(f"Taxonomy not found: {TAXONOMY_PATH}")
    
    with open(TAXONOMY_PATH) as f:
        return json.load(f)


def build_book_index(db_path: Path) -> List[Dict[str, Any]]:
    """
    Build book index from database.
    
    Returns list of:
    {
        "book_id": "...",
        "title": "...",
        "author": "...",
        "domain_ids": [...],
        "subdomain_ids": [...],
        "is_public": bool,
        "created_at": "..."
    }
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Fetch all books
    cursor.execute("""
        SELECT id, title, author, domain, subdomain, is_public, created_at
        FROM books
        ORDER BY title
    """)
    
    books = []
    for row in cursor.fetchall():
        book_id = row["id"]
        
        # Get taxonomy mapping (hardcoded for now)
        mapping = BOOK_TAXONOMY_MAPPINGS.get(book_id)
        
        if mapping:
            domain_ids = mapping["domain_ids"]
            subdomain_ids = mapping["subdomain_ids"]
        else:
            # Fallback: use domain/subdomain from DB
            domain = row["domain"]
            subdomain = row["subdomain"]
            
            # Map string domain to domain_id (lowercase)
            domain_ids = [domain.lower()] if domain else []
            subdomain_ids = [subdomain.lower()] if subdomain else []
        
        books.append({
            "book_id": book_id,
            "title": row["title"],
            "author": row["author"],
            "domain_ids": domain_ids,
            "subdomain_ids": subdomain_ids,
            "is_public": bool(row["is_public"]),
            "created_at": row["created_at"]
        })
    
    conn.close()
    return books


def build_chapter_index(db_path: Path) -> List[Dict[str, Any]]:
    """
    Build chapter index from database.
    
    Returns list of:
    {
        "chapter_id": "...",
        "book_id": "...",
        "number": int,
        "title": "...",
        "start_offset": int,
        "end_offset": int,
        "word_count": int (estimated),
        "headings": [] (optional, future)
    }
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Fetch all chapters
    cursor.execute("""
        SELECT 
            c.id as chapter_id,
            c.book_id,
            c.number,
            c.title,
            c.start_offset,
            c.end_offset,
            b.title as book_title
        FROM chapters c
        JOIN books b ON c.book_id = b.id
        ORDER BY b.title, c.number
    """)
    
    chapters = []
    for row in cursor.fetchall():
        # Estimate word count (rough: characters / 5)
        char_count = row["end_offset"] - row["start_offset"]
        word_count = char_count // 5
        
        chapters.append({
            "chapter_id": row["chapter_id"],
            "book_id": row["book_id"],
            "number": row["number"],
            "title": row["title"],
            "start_offset": row["start_offset"],
            "end_offset": row["end_offset"],
            "word_count": word_count,
            "headings": []  # Future: extract from PDF structure
        })
    
    conn.close()
    return chapters


def write_artifact(data: Dict[str, Any], filename: str):
    """Write artifact to JSON file with pretty printing."""
    output_path = ARTIFACTS_DIR / filename
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"✓ Wrote {output_path}")


def main():
    """Build artifacts from database."""
    print("=" * 80)
    print("ALEXANDRIA ARTIFACT BUILDER")
    print("=" * 80)
    
    # Check DB exists
    if not DB_PATH.exists():
        print(f"❌ Database not found: {DB_PATH}")
        return 1
    
    # Check taxonomy exists
    if not TAXONOMY_PATH.exists():
        print(f"❌ Taxonomy not found: {TAXONOMY_PATH}")
        print("   Create artifacts/taxonomy.v1.json first")
        return 1
    
    # Get next version
    current_version = get_current_version()
    next_version = current_version + 1
    print(f"\nCurrent version: {current_version}")
    print(f"Next version: {next_version}")
    
    # Load taxonomy for validation
    print("\n📖 Loading taxonomy...")
    taxonomy = load_taxonomy()
    print(f"   Domains: {len(taxonomy['domains'])}")
    
    # Build book index
    print("\n📚 Building book index...")
    books = build_book_index(DB_PATH)
    print(f"   Books found: {len(books)}")
    
    book_index = {
        "version": next_version,
        "taxonomy_version": taxonomy["version"],
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "total_books": len(books),
        "books": books
    }
    
    # Build chapter index
    print("\n📄 Building chapter index...")
    chapters = build_chapter_index(DB_PATH)
    print(f"   Chapters found: {len(chapters)}")
    
    chapter_index = {
        "version": next_version,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "total_chapters": len(chapters),
        "chapters": chapters
    }
    
    # Write artifacts
    print("\n💾 Writing artifacts...")
    write_artifact(book_index, f"book_index.v{next_version}.json")
    write_artifact(chapter_index, f"chapter_index.v{next_version}.json")
    
    # Print summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Books indexed: {len(books)}")
    print(f"Chapters indexed: {len(chapters)}")
    print(f"Version: {next_version}")
    
    print("\nBooks by domain:")
    domain_counts = {}
    for book in books:
        for domain_id in book["domain_ids"]:
            domain_counts[domain_id] = domain_counts.get(domain_id, 0) + 1
    
    for domain_id, count in sorted(domain_counts.items()):
        print(f"  {domain_id}: {count} books")
    
    print("\n✅ Artifacts built successfully")
    print(f"\nNext steps:")
    print(f"  1. Review artifacts/book_index.v{next_version}.json")
    print(f"  2. Review artifacts/chapter_index.v{next_version}.json")
    print(f"  3. Update taxonomy gate to use version {next_version}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
