#!/usr/bin/env python3
"""
Alexandria - Page Extraction

Extracts page-by-page text from PDFs and stores in database.
This creates the page-anchored foundation for everything else.

Usage:
    python -m admin.extract_pages batch1books/
    python -m admin.extract_pages batch1books/1984*.pdf --force
"""

import argparse
import hashlib
import sys
from pathlib import Path
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.database import init_db, get_supabase


def extract_pages_from_pdf(pdf_path: Path) -> List[Dict]:
    """
    Extract text from each page of a PDF.
    Returns list of {page_number, text, word_count, quality_score}.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        print("ERROR: pypdf not installed. Run: pip install pypdf")
        return []
    
    pages = []
    
    try:
        reader = PdfReader(pdf_path)
        total_pages = len(reader.pages)
        
        for i, page in enumerate(reader.pages):
            page_num = i + 1  # 1-indexed
            
            try:
                text = page.extract_text() or ""
            except Exception as e:
                text = ""
            
            # Clean text
            text = text.strip()
            
            # Calculate quality metrics
            word_count = len(text.split()) if text else 0
            
            # Quality score heuristics
            quality = 0.5
            if word_count > 200:
                quality += 0.2
            if word_count > 50:
                quality += 0.1
            if word_count < 10:
                quality -= 0.3
            
            # Check for OCR artifacts (lots of single chars)
            if text:
                single_chars = sum(1 for word in text.split() if len(word) == 1)
                if single_chars / max(word_count, 1) > 0.3:
                    quality -= 0.2
            
            quality = max(0.0, min(1.0, quality))
            
            pages.append({
                "page_number": page_num,
                "text": text,
                "word_count": word_count,
                "quality_score": round(quality, 2),
            })
        
        return pages
        
    except Exception as e:
        print(f"  ERROR extracting {pdf_path.name}: {e}")
        return []


def get_book_id_for_pdf(pdf_path: Path, client) -> Optional[str]:
    """Find the book_id for a given PDF path."""
    pdf_name = pdf_path.name
    
    # Try exact filename match in file_path
    result = client.table("books").select("id, title, file_path").execute()
    
    for book in result.data:
        if book.get("file_path"):
            stored_path = Path(book["file_path"])
            if stored_path.name == pdf_name:
                return book["id"]
    
    # Try title match
    # Extract title from filename (before " - ")
    title_guess = pdf_name.replace(".pdf", "").split(" - ")[0].strip()
    
    for book in result.data:
        if book["title"].lower().startswith(title_guess.lower()[:20]):
            return book["id"]
    
    return None


def store_pages(book_id: str, pages: List[Dict], client) -> int:
    """Store extracted pages in database."""
    stored = 0
    
    for page in pages:
        page_id = f"page_{book_id}_{page['page_number']}"
        
        try:
            client.table("book_pages").upsert({
                "id": page_id,
                "book_id": book_id,
                "page_number": page["page_number"],
                "page_text": page["text"],
                "text_quality": page["quality_score"],
                "word_count": page["word_count"],
                "has_images": 0,
                "is_scanned": 1 if page["quality_score"] < 0.3 else 0,
            }).execute()
            stored += 1
        except Exception as e:
            print(f"    Error storing page {page['page_number']}: {e}")
    
    return stored


def create_book_artifact_placeholder(book_id: str, total_pages: int, client):
    """Create a placeholder artifact record for bootstrap."""
    try:
        client.table("book_artifacts").upsert({
            "book_id": book_id,
            "artifact_version": 1,
            "bootstrap_status": "pending",
            "total_pages": total_pages,
            "structure_confidence": 0.0,
        }).execute()
    except Exception as e:
        print(f"    Note: Could not create artifact placeholder: {e}")


def process_pdf(pdf_path: Path, client, force: bool = False) -> Dict:
    """Process a single PDF file."""
    result = {
        "path": str(pdf_path),
        "status": "unknown",
        "pages": 0,
        "book_id": None,
    }
    
    # Find book_id
    book_id = get_book_id_for_pdf(pdf_path, client)
    if not book_id:
        result["status"] = "no_book_match"
        return result
    
    result["book_id"] = book_id
    
    # Check if already processed (unless force)
    if not force:
        existing = client.table("book_pages").select("id").eq("book_id", book_id).limit(1).execute()
        if existing.data:
            result["status"] = "already_processed"
            return result
    
    # Extract pages
    pages = extract_pages_from_pdf(pdf_path)
    if not pages:
        result["status"] = "extraction_failed"
        return result
    
    # Store pages
    stored = store_pages(book_id, pages, client)
    
    # Create artifact placeholder
    create_book_artifact_placeholder(book_id, len(pages), client)
    
    result["status"] = "success"
    result["pages"] = stored
    
    return result


def main():
    parser = argparse.ArgumentParser(description="Extract pages from PDFs")
    parser.add_argument("path", type=str, help="PDF file or directory")
    parser.add_argument("--force", action="store_true", help="Re-extract even if exists")
    parser.add_argument("--workers", type=int, default=4, help="Parallel workers")
    parser.add_argument("--limit", type=int, help="Limit number of PDFs to process")
    args = parser.parse_args()
    
    print("=" * 60)
    print("PAGE EXTRACTION")
    print("=" * 60)
    
    init_db()
    client = get_supabase()
    
    # Find PDFs to process
    target = Path(args.path)
    if target.is_file():
        pdfs = [target]
    elif target.is_dir():
        pdfs = sorted(target.glob("*.pdf"))
    else:
        # Glob pattern
        pdfs = sorted(Path(".").glob(args.path))
    
    if args.limit:
        pdfs = pdfs[:args.limit]
    
    print(f"PDFs to process: {len(pdfs)}")
    print(f"Force re-extract: {args.force}")
    print("=" * 60)
    
    # Process PDFs
    success = 0
    failed = 0
    skipped = 0
    no_match = 0
    
    for i, pdf_path in enumerate(pdfs):
        print(f"[{i+1}/{len(pdfs)}] {pdf_path.name[:50]}...")
        
        result = process_pdf(pdf_path, client, args.force)
        
        if result["status"] == "success":
            print(f"    ✅ {result['pages']} pages → {result['book_id'][:20]}")
            success += 1
        elif result["status"] == "already_processed":
            print(f"    ⏭️ Already processed")
            skipped += 1
        elif result["status"] == "no_book_match":
            print(f"    ⚠️ No matching book in DB")
            no_match += 1
        else:
            print(f"    ❌ {result['status']}")
            failed += 1
    
    print("=" * 60)
    print(f"Success: {success}")
    print(f"Skipped: {skipped}")
    print(f"No match: {no_match}")
    print(f"Failed: {failed}")
    print("=" * 60)


if __name__ == "__main__":
    main()
