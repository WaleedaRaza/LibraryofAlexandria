#!/usr/bin/env python3
"""
Alexandria - LLM Book Categorizer

Uses GPT to categorize books by domain based on title/author.
Updates the database with proper domains.

Usage:
    python -m admin.categorize_books
    python -m admin.categorize_books --dry-run
    python -m admin.categorize_books --batch-size 50
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.database import init_db, get_supabase
from app.config import settings

# Valid domains (from our taxonomy)
DOMAINS = [
    "Philosophy",
    "Strategy", 
    "Psychology",
    "Economics",
    "Business",
    "Technology",
    "History",
    "Politics",
    "Religion",
    "Science",
    "Literature",
    "Law",
    "Art",
    "Mathematics",
    "Sociology",
    "Medicine",
    "Communication",
]


def categorize_batch_with_llm(books: list) -> dict:
    """
    Use LLM to categorize a batch of books.
    Returns dict: book_id -> domain
    """
    import openai
    
    if not settings.OPENAI_API_KEY:
        print("ERROR: No OpenAI API key")
        return {}
    
    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
    
    # Format books for prompt
    books_list = "\n".join([
        f'{i+1}. "{b["title"]}" by {b["author"]} (id: {b["id"]})'
        for i, b in enumerate(books)
    ])
    
    domains_list = ", ".join(DOMAINS)
    
    prompt = f"""Categorize these books into domains.

VALID DOMAINS: {domains_list}

BOOKS:
{books_list}

For each book, assign the SINGLE most appropriate domain based on title and author.

Return JSON object mapping book_id to domain:
{{
  "book_xxx": "Philosophy",
  "book_yyy": "Psychology"
}}

Rules:
- Use ONLY the domains listed above
- Every book must get exactly one domain
- Base decision on title/author knowledge
- If truly unknown, use the most likely domain based on title words

Return ONLY valid JSON, no explanation."""

    response = client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=2000
    )
    
    result = response.choices[0].message.content.strip()
    
    # Parse JSON
    if result.startswith('```'):
        result = result.split('```')[1]
        if result.startswith('json'):
            result = result[4:]
        result = result.strip()
    
    try:
        return json.loads(result)
    except json.JSONDecodeError as e:
        print(f"JSON parse error: {e}")
        print(f"Raw response: {result[:500]}")
        return {}


def main():
    parser = argparse.ArgumentParser(description="Categorize books using LLM")
    parser.add_argument("--dry-run", action="store_true", help="Don't update DB")
    parser.add_argument("--batch-size", type=int, default=30, help="Books per LLM call")
    parser.add_argument("--domain", type=str, help="Only recategorize books in this domain")
    args = parser.parse_args()
    
    print("=" * 60)
    print("LLM BOOK CATEGORIZER")
    print("=" * 60)
    
    init_db()
    client = get_supabase()
    
    # Get books to categorize
    query = client.table("books").select("id, title, author, domain")
    
    if args.domain:
        query = query.eq("domain", args.domain)
    else:
        # Only categorize "General" or empty domain books
        query = query.or_("domain.eq.General,domain.is.null")
    
    result = query.execute()
    books = result.data
    
    print(f"Books to categorize: {len(books)}")
    print(f"Batch size: {args.batch_size}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print("=" * 60)
    
    if not books:
        print("No books to categorize!")
        return
    
    # Process in batches
    total_updated = 0
    all_updates = {}
    
    for i in range(0, len(books), args.batch_size):
        batch = books[i:i + args.batch_size]
        print(f"\n[Batch {i//args.batch_size + 1}] Processing {len(batch)} books...")
        
        try:
            categorizations = categorize_batch_with_llm(batch)
            
            for book_id, domain in categorizations.items():
                if domain in DOMAINS:
                    all_updates[book_id] = domain
                    print(f"  {book_id[:20]}: {domain}")
                else:
                    print(f"  {book_id[:20]}: INVALID DOMAIN '{domain}'")
            
        except Exception as e:
            print(f"  ERROR: {e}")
    
    print(f"\n{'=' * 60}")
    print(f"Total categorizations: {len(all_updates)}")
    
    # Update database
    if not args.dry_run and all_updates:
        print("\nUpdating database...")
        for book_id, domain in all_updates.items():
            try:
                client.table("books").update({"domain": domain}).eq("id", book_id).execute()
                total_updated += 1
            except Exception as e:
                print(f"  Error updating {book_id}: {e}")
        
        print(f"✅ Updated {total_updated} books")
    elif args.dry_run:
        print("\n🔍 DRY RUN - No changes made")
    
    print("=" * 60)


if __name__ == "__main__":
    main()
