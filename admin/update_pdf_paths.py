#!/usr/bin/env python3
"""
Update books with PDF file paths.

Matches books in the database to PDF files in batch1books/ 
based on title and author.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.database import init_db, get_supabase

PDF_DIR = Path(__file__).parent.parent / "batch1books"


def normalize(s: str) -> str:
    """Normalize string for matching."""
    return s.lower().replace("-", " ").replace("_", " ").replace("  ", " ").strip()


def find_pdf_for_book(title: str, author: str) -> Path | None:
    """Find PDF file matching a book."""
    title_norm = normalize(title)
    author_norm = normalize(author) if author else ""
    
    best_match = None
    best_score = 0
    
    for pdf in PDF_DIR.glob("*.pdf"):
        stem = pdf.stem
        stem_norm = normalize(stem)
        
        # Score the match
        score = 0
        
        # Title match
        if title_norm in stem_norm:
            score += 50
        elif title_norm[:20] in stem_norm:
            score += 30
        elif title_norm[:10] in stem_norm:
            score += 15
        
        # Author match
        if author_norm and author_norm.split()[0] in stem_norm:
            score += 25
        
        # Exact start match
        if stem_norm.startswith(title_norm[:15]):
            score += 20
        
        if score > best_score:
            best_score = score
            best_match = pdf
    
    # Only return if score is decent
    return best_match if best_score >= 30 else None


def main():
    print("=" * 60)
    print("UPDATE PDF PATHS")
    print("=" * 60)
    
    init_db()
    client = get_supabase()
    
    # Get all books
    result = client.table("books").select("id, title, author, file_path").execute()
    books = result.data
    
    print(f"Books in database: {len(books)}")
    print(f"PDF directory: {PDF_DIR}")
    print(f"PDFs available: {len(list(PDF_DIR.glob('*.pdf')))}")
    print("=" * 60)
    
    updated = 0
    not_found = []
    
    for book in books:
        book_id = book["id"]
        title = book["title"]
        author = book["author"]
        
        # Skip if already has valid path
        if book.get("file_path"):
            fp = Path(book["file_path"])
            if fp.exists():
                continue
        
        # Find PDF
        pdf = find_pdf_for_book(title, author)
        
        if pdf:
            # Store absolute path
            file_path = str(pdf.absolute())
            
            # Update database
            client.table("books").update({
                "file_path": file_path
            }).eq("id", book_id).execute()
            
            updated += 1
            print(f"✅ {title[:40]} → {pdf.name[:40]}")
        else:
            not_found.append(title)
    
    print("=" * 60)
    print(f"Updated: {updated}")
    print(f"Not found: {len(not_found)}")
    
    if not_found and len(not_found) <= 20:
        print("\nBooks without PDF match:")
        for title in not_found[:20]:
            print(f"  - {title}")
    
    print("=" * 60)


if __name__ == "__main__":
    main()
