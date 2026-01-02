#!/usr/bin/env python3
"""
Alexandria Library - Book Ingestion Tool

CLI tool to ingest books into the canon.
Admin use only.

Usage:
    python -m admin.ingest_books --pdf path/to/book.pdf --title "Book Title" --author "Author Name"
    python -m admin.ingest_books --dir path/to/pdfs/  # Batch ingest

This tool:
1. Extracts text from PDFs
2. Creates book entry in database
3. Stores full text in book_text table
4. Creates chapter boundaries (if possible)
"""

import argparse
import uuid
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.database import init_db, is_sqlite_mode, get_supabase
from app.config import settings


def extract_text_from_pdf(pdf_path: Path) -> str:
    """
    Extract text from a PDF file.
    
    Uses PyPDF2 or pdfplumber if available.
    Falls back to empty string if extraction fails.
    """
    try:
        import pypdf
        
        reader = pypdf.PdfReader(str(pdf_path))
        text_parts = []
        
        for page in reader.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)
        
        return "\n\n".join(text_parts)
    
    except ImportError:
        print("Warning: pypdf not installed. Run: pip install pypdf")
        return ""
    except Exception as e:
        print(f"Error extracting text from {pdf_path}: {e}")
        return ""


def parse_title_author_from_filename(filename: str) -> tuple:
    """
    Parse title and author from filename.
    
    Expected format: "Title - Author.pdf"
    """
    name = Path(filename).stem
    
    if " - " in name:
        parts = name.split(" - ", 1)
        title = parts[0].strip()
        author = parts[1].strip()
    else:
        title = name
        author = "Unknown"
    
    return title, author


def infer_domain(title: str, author: str) -> str:
    """
    Infer domain from title/author.
    Simple keyword matching.
    """
    text = f"{title} {author}".lower()
    
    if any(word in text for word in ["stoic", "marcus aurelius", "meditations", "philosophy", "plato", "aristotle"]):
        return "Philosophy"
    
    if any(word in text for word in ["war", "strategy", "sun tzu", "clausewitz", "machiavelli"]):
        return "Strategy"
    
    if any(word in text for word in ["security", "hacking", "cryptography", "software", "programming", "engineering"]):
        return "Technology"
    
    if any(word in text for word in ["psychology", "thinking", "behavior", "mind", "brain"]):
        return "Psychology"
    
    if any(word in text for word in ["economics", "market", "capitalism"]):
        return "Economics"
    
    if any(word in text for word in ["business", "management", "leadership"]):
        return "Business"
    
    return "Philosophy"  # Default


def create_simple_chapters(text: str, book_id: str) -> list:
    """
    Create simple chapter boundaries.
    
    For now, just splits by page breaks or large gaps.
    In production, use smarter heuristics or manual definition.
    """
    chapters = []
    chapter_id = f"ch_{uuid.uuid4().hex[:12]}"
    
    if is_sqlite_mode():
        from app.db.database import get_db
        db = get_db()
        db.execute(
            """
            INSERT INTO chapters (id, book_id, number, title, start_offset, end_offset)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (chapter_id, book_id, 1, "Full Text", 0, len(text))
        )
    else:
        client = get_supabase()
        client.table("chapters").insert({
            "id": chapter_id,
            "book_id": book_id,
            "number": 1,
            "title": "Full Text",
            "start_offset": 0,
            "end_offset": len(text)
        }).execute()
    
    chapters.append({
        "id": chapter_id,
        "number": 1,
        "title": "Full Text",
        "start_offset": 0,
        "end_offset": len(text)
    })
    
    return chapters


def ingest_pdf(
    pdf_path: Path,
    title: str = None,
    author: str = None,
    domain: str = None
) -> dict:
    """
    Ingest a single PDF into the canon.
    
    Returns dict with book info.
    """
    # Parse title/author from filename if not provided
    if not title or not author:
        parsed_title, parsed_author = parse_title_author_from_filename(pdf_path.name)
        title = title or parsed_title
        author = author or parsed_author
    
    # Infer domain if not provided
    domain = domain or infer_domain(title, author)
    
    # Extract text
    print(f"Extracting text from: {pdf_path.name}")
    text = extract_text_from_pdf(pdf_path)
    
    if not text:
        print(f"  Warning: No text extracted from {pdf_path.name}")
        text = "[Text extraction failed - manual input required]"
    
    # Create book entry
    book_id = f"book_{uuid.uuid4().hex[:12]}"
    word_count = len(text.split())
    
    if is_sqlite_mode():
        from app.db.database import get_db
        db = get_db()
        
        db.execute(
            """
            INSERT INTO books (id, title, author, domain, file_path, is_public)
            VALUES (?, ?, ?, ?, ?, 1)
            """,
            (book_id, title, author, domain, str(pdf_path))
        )
        
        db.execute(
            """
            INSERT INTO book_text (book_id, content, word_count)
            VALUES (?, ?, ?)
            """,
            (book_id, text, word_count)
        )
        
        # Create chapters
        chapters = create_simple_chapters(text, book_id)
        
        db.commit()
    else:
        # Supabase REST API
        client = get_supabase()
        
        client.table("books").insert({
            "id": book_id,
            "title": title,
            "author": author,
            "domain": domain,
            "file_path": str(pdf_path),
            "is_public": 1  # INTEGER column: 1=public, 0=private
        }).execute()
        
        client.table("book_text").insert({
            "book_id": book_id,
            "content": text,
            "word_count": word_count
        }).execute()
        
        # Create chapters
        chapters = create_simple_chapters(text, book_id)
    
    print(f"  ✓ Ingested: {title} by {author}")
    print(f"    Domain: {domain}")
    print(f"    Words: {word_count}")
    print(f"    Chapters: {len(chapters)}")
    
    return {
        "id": book_id,
        "title": title,
        "author": author,
        "domain": domain,
        "word_count": word_count,
        "chapters": len(chapters)
    }


def ingest_directory(dir_path: Path) -> list:
    """
    Ingest all PDFs in a directory.
    """
    results = []
    
    pdf_files = list(dir_path.glob("*.pdf"))
    print(f"Found {len(pdf_files)} PDF files")
    
    for pdf_path in pdf_files:
        try:
            result = ingest_pdf(pdf_path)
            results.append(result)
        except Exception as e:
            print(f"  ✗ Error ingesting {pdf_path.name}: {e}")
    
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Ingest books into Alexandria Library"
    )
    parser.add_argument("--pdf", type=Path, help="Path to a single PDF file")
    parser.add_argument("--dir", type=Path, help="Path to directory of PDFs")
    parser.add_argument("--title", type=str, help="Book title (optional)")
    parser.add_argument("--author", type=str, help="Book author (optional)")
    parser.add_argument("--domain", type=str, help="Book domain (optional)")
    
    args = parser.parse_args()
    
    # Show database mode
    print("=" * 50)
    if is_sqlite_mode():
        print("📁 Database: SQLite (local)")
    else:
        print("☁️  Database: Supabase REST API")
    print("=" * 50)
    
    # Initialize database
    init_db()
    
    if args.pdf:
        if not args.pdf.exists():
            print(f"Error: File not found: {args.pdf}")
            sys.exit(1)
        
        ingest_pdf(args.pdf, args.title, args.author, args.domain)
    
    elif args.dir:
        if not args.dir.exists():
            print(f"Error: Directory not found: {args.dir}")
            sys.exit(1)
        
        results = ingest_directory(args.dir)
        print(f"\nIngested {len(results)} books")
    
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
