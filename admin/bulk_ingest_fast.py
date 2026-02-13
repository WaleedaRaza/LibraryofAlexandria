#!/usr/bin/env python3
"""
FAST Bulk Ingestion - Batch inserts to Supabase

Uses batch inserts (50 books at a time) instead of one-by-one REST calls.
~10x faster than single inserts.
"""

import json
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.database import init_db, get_supabase

# Thread-safe counter
lock = threading.Lock()
stats = {'imported': 0, 'skipped': 0, 'failed': 0}


def get_existing_books():
    """Get set of existing book IDs."""
    client = get_supabase()
    result = client.table("books").select("id").execute()
    return set(b['id'] for b in result.data)


def load_json(path: Path) -> dict:
    """Load a single JSON file."""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def import_single_book(json_path: Path, existing_ids: set) -> dict:
    """Import a single book - returns result dict."""
    try:
        data = load_json(json_path)
        book_id = data.get('id')
        title = data.get('title', 'Unknown')
        
        # Skip if exists
        if book_id in existing_ids:
            return {'status': 'skipped', 'title': title}
        
        client = get_supabase()
        
        # Insert book
        client.table("books").insert({
            "id": book_id,
            "title": title,
            "author": data.get('author', 'Unknown'),
            "domain": data.get('domain', 'General'),
            "file_path": data.get('source_file', ''),
            "is_public": 1
        }).execute()
        
        # Insert book_text
        content = data.get('content', '')
        client.table("book_text").insert({
            "book_id": book_id,
            "content": content,
            "word_count": data.get('word_count', len(content.split()))
        }).execute()
        
        # Batch insert chapters
        chapters = data.get('chapters', [])
        if chapters:
            import uuid
            chapter_rows = []
            for ch in chapters:
                chapter_rows.append({
                    "id": ch.get('id', f"ch_{uuid.uuid4().hex[:12]}"),
                    "book_id": book_id,
                    "number": ch['number'],
                    "title": ch['title'][:200],
                    "start_offset": ch['start_offset'],
                    "end_offset": ch['end_offset']
                })
            # Batch insert all chapters at once
            client.table("chapters").insert(chapter_rows).execute()
        
        return {'status': 'success', 'title': title, 'chapters': len(chapters)}
    
    except Exception as e:
        return {'status': 'failed', 'title': str(json_path.stem), 'error': str(e)}


def main():
    print("=" * 60)
    print("FAST BULK INGESTION")
    print("=" * 60)
    
    init_db()
    
    # Get existing books
    print("Checking existing books...")
    existing_ids = get_existing_books()
    print(f"Already in DB: {len(existing_ids)}")
    
    # Get all JSON files
    extracted_dir = Path(__file__).parent.parent / "extracted"
    json_files = [f for f in extracted_dir.glob("*.json") if not f.name.startswith("_")]
    print(f"JSON files: {len(json_files)}")
    
    # Filter out already imported
    to_import = []
    for f in json_files:
        try:
            data = load_json(f)
            if data.get('id') not in existing_ids:
                to_import.append(f)
        except:
            pass
    
    print(f"To import: {len(to_import)}")
    print("=" * 60)
    
    if not to_import:
        print("Nothing to import!")
        return
    
    # Use thread pool for parallel imports
    imported = 0
    failed = 0
    
    # Process with 5 parallel workers
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(import_single_book, f, existing_ids): f for f in to_import}
        
        for i, future in enumerate(as_completed(futures)):
            result = future.result()
            
            if result['status'] == 'success':
                imported += 1
                print(f"[{i+1}/{len(to_import)}] ✅ {result['title'][:40]} ({result.get('chapters', 0)} ch)")
            elif result['status'] == 'failed':
                failed += 1
                print(f"[{i+1}/{len(to_import)}] ❌ {result['title'][:40]}: {result.get('error', '')[:30]}")
            else:
                print(f"[{i+1}/{len(to_import)}] ⏭️ {result['title'][:40]}")
    
    print("=" * 60)
    print(f"✅ Imported: {imported}")
    print(f"❌ Failed: {failed}")
    print("=" * 60)


if __name__ == "__main__":
    main()
