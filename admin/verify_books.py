#!/usr/bin/env python3
"""
Alexandria Library - Book Verification Script

Checks:
1. How many books are in the database
2. How many JSON files exist in extracted/
3. Which books are missing from database
4. Which books have poor extraction quality (single chapter, etc.)

Usage:
    python -m admin.verify_books
    python -m admin.verify_books --detailed  # Show per-book breakdown
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Set
from collections import defaultdict

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.database import init_db, is_sqlite_mode, get_supabase
from app.config import settings


def get_db_books() -> Dict[str, Dict]:
    """Get all books from database. Returns {book_id: {title, author, domain}}"""
    books = {}
    
    if is_sqlite_mode():
        from app.db.database import get_db
        db = get_db()
        rows = db.execute(
            "SELECT id, title, author, domain FROM books"
        ).fetchall()
        for row in rows:
            books[row['id']] = {
                'title': row['title'],
                'author': row['author'],
                'domain': row.get('domain', 'Unknown')
            }
    else:
        client = get_supabase()
        result = client.table("books").select("id, title, author, domain").execute()
        for book in result.data:
            books[book['id']] = {
                'title': book['title'],
                'author': book['author'],
                'domain': book.get('domain', 'Unknown')
            }
    
    return books


def get_json_books(extracted_dir: Path) -> Dict[str, Dict]:
    """Get all books from JSON files. Returns {book_id: {title, author, chapters, method}}"""
    books = {}
    
    if not extracted_dir.exists():
        return books
    
    for json_file in extracted_dir.glob("*.json"):
        # Skip summary/report files
        if json_file.name.startswith('_'):
            continue
        
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            book_id = data.get('id')
            if not book_id:
                continue
            
            chapters = data.get('chapters', [])
            books[book_id] = {
                'title': data.get('title', 'Unknown'),
                'author': data.get('author', 'Unknown'),
                'chapters': len(chapters),
                'method': data.get('extraction_method', 'unknown'),
                'file': str(json_file),
                'word_count': data.get('word_count', 0),
                'has_single_chapter': len(chapters) == 1
            }
        except Exception as e:
            print(f"  ⚠️  Error reading {json_file.name}: {e}")
    
    return books


def analyze_extraction_quality(json_books: Dict) -> Dict:
    """Analyze extraction quality metrics."""
    stats = {
        'total': len(json_books),
        'by_method': defaultdict(int),
        'by_chapter_count': defaultdict(int),
        'single_chapter': 0,
        'poor_quality': []  # Books with single chapter or suspicious patterns
    }
    
    for book_id, book in json_books.items():
        method = book.get('method', 'unknown')
        chapters = book.get('chapters', 0)
        
        stats['by_method'][method] += 1
        stats['by_chapter_count'][chapters] += 1
        
        if chapters == 1:
            stats['single_chapter'] += 1
            stats['poor_quality'].append({
                'id': book_id,
                'title': book['title'],
                'author': book['author'],
                'reason': 'single_chapter'
            })
    
    return stats


def find_missing_books(db_books: Dict, json_books: Dict) -> List[Dict]:
    """Find books that exist in JSON but not in database."""
    missing = []
    
    db_keys = set(db_books.keys())
    
    for book_id, book_data in json_books.items():
        if book_id not in db_keys:
            # Also check by title/author in case ID mismatch
            title = book_data['title']
            author = book_data['author']
            found = False
            
            for db_id, db_book in db_books.items():
                if db_book['title'] == title and db_book['author'] == author:
                    found = True
                    break
            
            if not found:
                missing.append({
                    'id': book_id,
                    'title': title,
                    'author': author,
                    'file': book_data.get('file', 'unknown'),
                    'chapters': book_data.get('chapters', 0),
                    'method': book_data.get('method', 'unknown')
                })
    
    return missing


def main():
    parser = argparse.ArgumentParser(description="Verify book ingestion status")
    parser.add_argument(
        '--extracted-dir',
        type=Path,
        default=Path(__file__).parent.parent / 'extracted',
        help='Directory containing extracted JSON files'
    )
    parser.add_argument(
        '--detailed',
        action='store_true',
        help='Show detailed per-book breakdown'
    )
    args = parser.parse_args()
    
    print("=" * 70)
    print("ALEXANDRIA BOOK VERIFICATION")
    print("=" * 70)
    print()
    
    # Initialize database connection (optional - may fail if no env vars)
    db_books = {}
    try:
        init_db()
        # Get books from database
        print("📊 Loading books from database...")
        db_books = get_db_books()
        print(f"   Found {len(db_books)} books in database")
        print()
    except Exception as e:
        print("⚠️  Could not connect to database (this is OK for JSON-only analysis)")
        print(f"   Error: {e}")
        print()
        print("   Continuing with JSON file analysis only...")
        print()
    
    # Get books from JSON files
    print(f"📁 Loading books from {args.extracted_dir}...")
    json_books = get_json_books(args.extracted_dir)
    print(f"   Found {len(json_books)} JSON files")
    print()
    
    # Analyze extraction quality
    print("🔍 Analyzing extraction quality...")
    quality_stats = analyze_extraction_quality(json_books)
    
    print(f"   Total extracted: {quality_stats['total']}")
    print(f"   Single chapter (poor quality): {quality_stats['single_chapter']} ({quality_stats['single_chapter']/quality_stats['total']*100:.1f}%)")
    print()
    print("   By extraction method:")
    for method, count in sorted(quality_stats['by_method'].items()):
        print(f"     {method:12} {count:4} books")
    print()
    
    # Find missing books (only if we have DB connection)
    missing = []
    if db_books:
        print("🔎 Finding missing books...")
        missing = find_missing_books(db_books, json_books)
        print(f"   {len(missing)} books in JSON but not in database")
        print()
    
    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    if db_books:
        print(f"Database books:     {len(db_books):4}")
    else:
        print(f"Database books:     (not connected)")
    print(f"Extracted JSON:     {len(json_books):4}")
    if db_books:
        print(f"Missing from DB:    {len(missing):4}")
    print(f"Poor quality:       {quality_stats['single_chapter']:4} ({quality_stats['single_chapter']/quality_stats['total']*100:.1f}%)")
    print()
    
    if db_books:
        if missing:
            print(f"⚠️  {len(missing)} books need to be ingested!")
            if args.detailed:
                print()
                print("Missing books:")
                for book in missing[:20]:  # Show first 20
                    print(f"  - {book['title']} by {book['author']} ({book['chapters']} chapters, {book['method']})")
                if len(missing) > 20:
                    print(f"  ... and {len(missing) - 20} more")
            print()
            print("To ingest missing books:")
            print(f"  python -m admin.ingest_from_json {args.extracted_dir}")
        else:
            print("✅ All extracted books are in the database!")
    else:
        print("⚠️  Database not connected - cannot check ingestion status")
        print()
        print("To ingest all books:")
        print(f"  python -m admin.ingest_from_json {args.extracted_dir}")
    
    if quality_stats['single_chapter'] > 0:
        print()
        print(f"⚠️  {quality_stats['single_chapter']} books have poor extraction quality (single chapter)")
        print("   These may need re-extraction with LLM pass:")
        print(f"   python -m admin.extract_chapters batch1books/ extracted/ --llm")
    
    print()


if __name__ == '__main__':
    main()
