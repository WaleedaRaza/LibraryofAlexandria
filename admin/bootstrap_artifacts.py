#!/usr/bin/env python3
"""
Alexandria - Bootstrap Book Artifacts

Runs the BookAgent to create initial artifacts for books that have pages extracted.

Usage:
    python -m admin.bootstrap_artifacts               # All pending books
    python -m admin.bootstrap_artifacts --book-id X   # Specific book
    python -m admin.bootstrap_artifacts --limit 10    # First 10 pending
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.database import init_db, get_supabase
from app.agents.book_agent import BookAgent, PageSample
from app.domain.book_artifacts import BookArtifacts


def get_pages_for_book(book_id: str, client) -> list:
    """Fetch all pages for a book from database."""
    result = client.table("book_pages").select(
        "page_number, page_text, word_count, text_quality"
    ).eq("book_id", book_id).order("page_number").execute()
    
    pages = []
    for row in result.data:
        pages.append(PageSample(
            page_number=row["page_number"],
            text=row["page_text"] or "",
            word_count=row["word_count"] or 0,
            quality=row["text_quality"] or 0.5,
        ))
    
    return pages


def store_artifacts(artifacts: BookArtifacts, client):
    """Store BookArtifacts in database."""
    # Update book_artifacts master record
    client.table("book_artifacts").upsert({
        "book_id": artifacts.book_id,
        "artifact_version": artifacts.version,
        "bootstrap_status": artifacts.status,
        "total_pages": artifacts.total_pages,
        "structure_confidence": artifacts.structure_confidence,
        "last_bootstrap": "now()",
        "external_profile": artifacts.external_profile.to_json() if artifacts.external_profile else None,
    }).execute()
    
    # Store sections
    for section in artifacts.sections:
        client.table("book_sections").upsert({
            "id": section.id,
            "book_id": artifacts.book_id,
            "section_type": section.section_type.value,
            "title": section.title,
            "page_start": section.pages.start,
            "page_end": section.pages.end,
            "parent_id": section.parent_id,
            "section_order": section.order,
            "confidence": section.confidence,
            "provenance": section.provenance.value,
        }).execute()
    
    # Store landmarks
    for landmark in artifacts.all_landmarks:
        client.table("book_landmarks").upsert({
            "id": landmark.id,
            "book_id": artifacts.book_id,
            "landmark_type": landmark.landmark_type.value,
            "label": landmark.label,
            "description": landmark.description,
            "page_start": landmark.pages.start,
            "page_end": landmark.pages.end,
            "importance": landmark.importance,
            "confidence": landmark.confidence,
            "provenance": landmark.provenance.value,
            "related_landmarks": ",".join(landmark.related_ids) if landmark.related_ids else None,
        }).execute()
    
    # Store reading paths
    for path in artifacts.paths:
        import json
        client.table("book_paths").upsert({
            "id": path.id,
            "book_id": artifacts.book_id,
            "path_goal": path.goal,
            "path_name": path.name,
            "steps": json.dumps([s.to_dict() for s in path.steps]),
        }).execute()


def get_pending_books(client, limit: int = None) -> list:
    """Get books that need artifact bootstrapping."""
    # Books with pages but no complete artifacts
    query = client.table("book_artifacts").select(
        "book_id, bootstrap_status"
    ).neq("bootstrap_status", "complete")
    
    if limit:
        query = query.limit(limit)
    
    result = query.execute()
    
    pending_ids = [r["book_id"] for r in result.data]
    
    if not pending_ids:
        return []
    
    # Get book details
    books = []
    for book_id in pending_ids:
        book_result = client.table("books").select(
            "id, title, author"
        ).eq("id", book_id).execute()
        
        if book_result.data:
            books.append(book_result.data[0])
    
    return books


def bootstrap_book(book: dict, client, with_research: bool = False) -> str:
    """Bootstrap artifacts for a single book."""
    book_id = book["id"]
    title = book["title"]
    author = book["author"]
    
    # Get pages
    pages = get_pages_for_book(book_id, client)
    
    if not pages:
        return "no_pages"
    
    # Create agent
    agent = BookAgent(book_id, title, author)
    
    # Bootstrap artifacts
    artifacts = agent.bootstrap(pages)
    
    # Optionally research external context
    if with_research:
        artifacts.external_profile = agent.research_external()
    
    # Store artifacts
    store_artifacts(artifacts, client)
    
    return artifacts.status


def main():
    parser = argparse.ArgumentParser(description="Bootstrap book artifacts")
    parser.add_argument("--book-id", type=str, help="Specific book ID")
    parser.add_argument("--limit", type=int, help="Limit number of books")
    parser.add_argument("--research", action="store_true", help="Also fetch external research")
    args = parser.parse_args()
    
    print("=" * 60)
    print("BOOTSTRAP BOOK ARTIFACTS")
    print("=" * 60)
    
    init_db()
    client = get_supabase()
    
    # Get books to process
    if args.book_id:
        result = client.table("books").select("id, title, author").eq("id", args.book_id).execute()
        books = result.data
    else:
        books = get_pending_books(client, args.limit)
    
    print(f"Books to bootstrap: {len(books)}")
    print(f"Include research: {args.research}")
    print("=" * 60)
    
    success = 0
    failed = 0
    no_pages = 0
    
    for i, book in enumerate(books):
        print(f"[{i+1}/{len(books)}] {book['title'][:50]}...")
        
        try:
            status = bootstrap_book(book, client, args.research)
            
            if status == "complete":
                print(f"    ✅ Artifacts created")
                success += 1
            elif status == "no_pages":
                print(f"    ⚠️ No pages extracted yet")
                no_pages += 1
            else:
                print(f"    ❌ {status}")
                failed += 1
                
        except Exception as e:
            print(f"    ❌ Error: {e}")
            failed += 1
    
    print("=" * 60)
    print(f"Success: {success}")
    print(f"No pages: {no_pages}")
    print(f"Failed: {failed}")
    print("=" * 60)


if __name__ == "__main__":
    main()
