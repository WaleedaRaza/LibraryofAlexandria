#!/usr/bin/env python3
"""
Alexandria Library - JSON to Database Ingestion

Takes the extracted JSON files from extract_chapters.py and imports them into
the database (Supabase or SQLite).

Usage:
    python -m admin.ingest_from_json extracted/
    python -m admin.ingest_from_json extracted/single_book.json
    python -m admin.ingest_from_json extracted/ --dry-run  # Preview without importing

This tool:
1. Reads pre-extracted JSON files
2. Creates book entry in database
3. Stores full text in book_text table
4. Creates chapter boundaries with proper offsets
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timezone

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.database import init_db, is_sqlite_mode, get_supabase
from app.config import settings


def check_duplicate(title: str, author: str) -> Optional[str]:
    """
    Check if a book with this title/author already exists.
    Returns existing book_id if found, None otherwise.
    """
    if is_sqlite_mode():
        from app.db.database import get_db
        db = get_db()
        row = db.execute(
            "SELECT id FROM books WHERE title = ? AND author = ?",
            (title, author)
        ).fetchone()
        return row[0] if row else None
    else:
        client = get_supabase()
        result = client.table("books").select("id").eq("title", title).eq("author", author).execute()
        if result.data and len(result.data) > 0:
            return result.data[0]['id']
        return None


def ingest_json_file(
    json_path: Path, 
    dry_run: bool = False,
    skip_duplicates: bool = True,
    verbose: bool = True
) -> Dict:
    """
    Ingest a single extracted JSON file into the database.
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    title = data.get('title', 'Unknown')
    author = data.get('author', 'Unknown')
    book_id = data.get('id')
    
    result = {
        'file': str(json_path),
        'title': title,
        'author': author,
        'status': 'pending'
    }
    
    # Check for duplicates
    if skip_duplicates:
        existing_id = check_duplicate(title, author)
        if existing_id:
            result['status'] = 'skipped'
            result['reason'] = f'Duplicate exists: {existing_id}'
            if verbose:
                print(f"  ⏭️  Skipped (duplicate): {title}")
            return result
    
    if dry_run:
        result['status'] = 'dry_run'
        result['would_create'] = {
            'book_id': book_id,
            'title': title,
            'author': author,
            'domain': data.get('domain', 'General'),
            'word_count': data.get('word_count', 0),
            'chapter_count': len(data.get('chapters', []))
        }
        return result
    
    # Insert into database
    try:
        content = data.get('content', '')
        word_count = data.get('word_count', len(content.split()))
        domain = data.get('domain', 'General')
        chapters = data.get('chapters', [])
        source_file = data.get('source_file', '')
        
        if is_sqlite_mode():
            from app.db.database import get_db
            db = get_db()
            
            # Insert book
            db.execute(
                """
                INSERT INTO books (id, title, author, domain, file_path, is_public)
                VALUES (?, ?, ?, ?, ?, 1)
                """,
                (book_id, title, author, domain, source_file)
            )
            
            # Insert book_text
            db.execute(
                """
                INSERT INTO book_text (book_id, content, word_count)
                VALUES (?, ?, ?)
                """,
                (book_id, content, word_count)
            )
            
            # Insert chapters
            for ch in chapters:
                import uuid
                chapter_id = ch.get('id', f"ch_{uuid.uuid4().hex[:12]}")
                db.execute(
                    """
                    INSERT INTO chapters (id, book_id, number, title, start_offset, end_offset)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (chapter_id, book_id, ch['number'], ch['title'], 
                     ch['start_offset'], ch['end_offset'])
                )
            
            db.commit()
            
        else:
            # Supabase REST API
            client = get_supabase()
            
            # Insert book
            client.table("books").insert({
                "id": book_id,
                "title": title,
                "author": author,
                "domain": domain,
                "file_path": source_file,
                "is_public": 1
            }).execute()
            
            # Insert book_text
            client.table("book_text").insert({
                "book_id": book_id,
                "content": content,
                "word_count": word_count
            }).execute()
            
            # Insert chapters
            for ch in chapters:
                import uuid
                chapter_id = ch.get('id', f"ch_{uuid.uuid4().hex[:12]}")
                client.table("chapters").insert({
                    "id": chapter_id,
                    "book_id": book_id,
                    "number": ch['number'],
                    "title": ch['title'],
                    "start_offset": ch['start_offset'],
                    "end_offset": ch['end_offset']
                }).execute()
        
        result['status'] = 'success'
        result['book_id'] = book_id
        result['chapters_created'] = len(chapters)
        
        if verbose:
            print(f"  ✅ Imported: {title} ({len(chapters)} chapters)")
        
    except Exception as e:
        result['status'] = 'failed'
        result['error'] = str(e)
        if verbose:
            print(f"  ❌ Failed: {title} - {e}")
    
    return result


def ingest_directory(
    input_dir: Path,
    dry_run: bool = False,
    skip_duplicates: bool = True,
    verbose: bool = True
) -> Dict:
    """Ingest all JSON files in a directory."""
    json_files = sorted(input_dir.glob('*.json'))
    
    # Skip summary files
    json_files = [f for f in json_files if not f.name.startswith('_')]
    
    print(f"\n{'='*60}")
    print(f"ALEXANDRIA DATABASE INGESTION")
    print(f"{'='*60}")
    print(f"Input:        {input_dir}")
    print(f"JSON files:   {len(json_files)}")
    print(f"Database:     {'SQLite' if is_sqlite_mode() else 'Supabase'}")
    print(f"Mode:         {'DRY RUN' if dry_run else 'LIVE'}")
    print(f"{'='*60}\n")
    
    results = {
        'total': len(json_files),
        'success': [],
        'failed': [],
        'skipped': []
    }
    
    for i, json_file in enumerate(json_files):
        print(f"[{i+1:3d}/{len(json_files)}] {json_file.name[:50]}...")
        
        try:
            result = ingest_json_file(
                json_file, 
                dry_run=dry_run, 
                skip_duplicates=skip_duplicates,
                verbose=verbose
            )
            
            if result['status'] == 'success':
                results['success'].append(result)
            elif result['status'] == 'skipped':
                results['skipped'].append(result)
            elif result['status'] == 'dry_run':
                results['success'].append(result)
            else:
                results['failed'].append(result)
                
        except Exception as e:
            results['failed'].append({
                'file': str(json_file),
                'status': 'failed',
                'error': str(e)
            })
            print(f"  ❌ Exception: {e}")
    
    # Print summary
    print(f"\n{'='*60}")
    print(f"INGESTION COMPLETE")
    print(f"{'='*60}")
    if dry_run:
        print(f"🔍 DRY RUN - No changes made")
        print(f"Would import: {len(results['success'])}/{results['total']}")
    else:
        print(f"✅ Imported:  {len(results['success'])}/{results['total']}")
    print(f"⏭️  Skipped:   {len(results['skipped'])}/{results['total']}")
    print(f"❌ Failed:    {len(results['failed'])}/{results['total']}")
    print(f"{'='*60}\n")
    
    # Save report
    report_file = input_dir / '_ingestion_report.json'
    with open(report_file, 'w') as f:
        json.dump({
            'ingestion_date': datetime.now(timezone.utc).isoformat(),
            'dry_run': dry_run,
            'database_mode': 'sqlite' if is_sqlite_mode() else 'supabase',
            'total': results['total'],
            'successful': len(results['success']),
            'skipped': len(results['skipped']),
            'failed': len(results['failed']),
            'failed_details': results['failed']
        }, f, indent=2)
    
    print(f"Report saved to: {report_file}")
    
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Import extracted JSON files into Alexandria database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Import all extracted books
    python -m admin.ingest_from_json extracted/
    
    # Dry run (preview without importing)
    python -m admin.ingest_from_json extracted/ --dry-run
    
    # Import a single book
    python -m admin.ingest_from_json extracted/1984.json
    
    # Import without duplicate checking
    python -m admin.ingest_from_json extracted/ --allow-duplicates
"""
    )
    parser.add_argument("input", type=Path, help="Input JSON file or directory")
    parser.add_argument("--dry-run", action="store_true", help="Preview without importing")
    parser.add_argument("--allow-duplicates", action="store_true", help="Don't skip duplicates")
    parser.add_argument("-q", "--quiet", action="store_true", help="Less verbose output")
    
    args = parser.parse_args()
    
    if not args.input.exists():
        print(f"ERROR: Input not found: {args.input}")
        sys.exit(1)
    
    # Initialize database
    print("Initializing database connection...")
    init_db()
    
    if args.input.is_file():
        # Single file
        result = ingest_json_file(
            args.input, 
            dry_run=args.dry_run,
            skip_duplicates=not args.allow_duplicates,
            verbose=not args.quiet
        )
        if result['status'] == 'success':
            print(f"\n✅ Imported: {result['title']}")
            print(f"   Book ID: {result['book_id']}")
            print(f"   Chapters: {result['chapters_created']}")
        elif result['status'] == 'dry_run':
            print(f"\n🔍 DRY RUN: Would import {result['title']}")
        elif result['status'] == 'skipped':
            print(f"\n⏭️  Skipped: {result['reason']}")
        else:
            print(f"\n❌ Failed: {result.get('error', 'Unknown error')}")
            sys.exit(1)
    else:
        # Directory
        ingest_directory(
            args.input,
            dry_run=args.dry_run,
            skip_duplicates=not args.allow_duplicates,
            verbose=not args.quiet
        )


if __name__ == "__main__":
    main()
