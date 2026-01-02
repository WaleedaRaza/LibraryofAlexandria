#!/usr/bin/env python3
"""
Alexandria Library - Seed Books
Populates the database with sample books for testing.

Usage:
    python -m admin.seed_books
"""

import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.database import get_supabase, is_sqlite_mode, init_db
from app.config import settings


# =============================================================================
# SEED DATA - Classic texts across domains
# =============================================================================

SEED_BOOKS = [
    # Philosophy
    {
        "id": "book_meditations",
        "title": "Meditations",
        "author": "Marcus Aurelius",
        "domain": "Philosophy",
        "subdomain": "Stoicism",
        "is_public": 1,
        "chapters": [
            {"number": 1, "title": "Book I - Debts and Lessons"},
            {"number": 2, "title": "Book II - On the River Gran"},
            {"number": 3, "title": "Book III - In Carnuntum"},
            {"number": 4, "title": "Book IV - In Retreat"},
        ]
    },
    {
        "id": "book_enchiridion",
        "title": "Enchiridion (The Manual)",
        "author": "Epictetus",
        "domain": "Philosophy",
        "subdomain": "Stoicism",
        "is_public": 1,
        "chapters": [
            {"number": 1, "title": "What is in our power"},
            {"number": 2, "title": "How to act with things"},
            {"number": 3, "title": "The discipline of desire"},
        ]
    },
    {
        "id": "book_republic",
        "title": "The Republic",
        "author": "Plato",
        "domain": "Philosophy",
        "subdomain": "Political Philosophy",
        "is_public": 1,
        "chapters": [
            {"number": 1, "title": "Book I - Justice"},
            {"number": 2, "title": "Book II - The Challenge"},
            {"number": 3, "title": "Book VII - The Cave"},
        ]
    },
    # Strategy
    {
        "id": "book_art_of_war",
        "title": "The Art of War",
        "author": "Sun Tzu",
        "domain": "Strategy",
        "subdomain": "Military Strategy",
        "is_public": 1,
        "chapters": [
            {"number": 1, "title": "Laying Plans"},
            {"number": 2, "title": "Waging War"},
            {"number": 3, "title": "Attack by Stratagem"},
            {"number": 4, "title": "Tactical Dispositions"},
        ]
    },
    {
        "id": "book_prince",
        "title": "The Prince",
        "author": "Niccolò Machiavelli",
        "domain": "Strategy",
        "subdomain": "Political Strategy",
        "is_public": 1,
        "chapters": [
            {"number": 1, "title": "How Many Kinds of Principalities There Are"},
            {"number": 2, "title": "Concerning Hereditary Principalities"},
            {"number": 3, "title": "Concerning Mixed Principalities"},
        ]
    },
    # Psychology
    {
        "id": "book_thinking_fast_slow",
        "title": "Thinking, Fast and Slow",
        "author": "Daniel Kahneman",
        "domain": "Psychology",
        "subdomain": "Cognitive Psychology",
        "is_public": 1,
        "chapters": [
            {"number": 1, "title": "The Characters of the Story"},
            {"number": 2, "title": "Attention and Effort"},
            {"number": 3, "title": "The Lazy Controller"},
        ]
    },
    # Technology
    {
        "id": "book_mythical_man_month",
        "title": "The Mythical Man-Month",
        "author": "Frederick P. Brooks Jr.",
        "domain": "Technology",
        "subdomain": "Software Engineering",
        "is_public": 1,
        "chapters": [
            {"number": 1, "title": "The Tar Pit"},
            {"number": 2, "title": "The Mythical Man-Month"},
            {"number": 3, "title": "The Surgical Team"},
        ]
    },
    # Economics
    {
        "id": "book_wealth_nations",
        "title": "The Wealth of Nations",
        "author": "Adam Smith",
        "domain": "Economics",
        "subdomain": "Political Economy",
        "is_public": 1,
        "chapters": [
            {"number": 1, "title": "Of the Division of Labour"},
            {"number": 2, "title": "Of the Principle which gives Occasion to the Division of Labour"},
            {"number": 3, "title": "That the Division of Labour is Limited by the Extent of the Market"},
        ]
    },
]

# Sample text content for each book
SAMPLE_TEXT = """This is sample text content for the book. In a real deployment, this would contain 
the actual full text of the book, extracted from PDF or other sources.

The text would be divided into chapters, with each chapter having a start_offset and end_offset
that references positions in this content field.

This sample content is repeated to provide enough text for demonstration purposes.
Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore
et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris.

Chapter content would continue here with the actual philosophical, strategic, or technical content
from the source material. The agents use this text to provide recommendations and the text companion
uses it to explain passages when users highlight and ask questions.
"""


def seed_supabase():
    """Seed books into Supabase."""
    client = get_supabase()
    
    print("🌱 Seeding Supabase with sample books...")
    
    for book_data in SEED_BOOKS:
        book_id = book_data["id"]
        chapters = book_data.pop("chapters")
        
        # Check if book already exists
        existing = client.table("books").select("id").eq("id", book_id).execute()
        if existing.data:
            print(f"  ⏭️  {book_data['title']} already exists, skipping")
            continue
        
        # Insert book
        client.table("books").insert(book_data).execute()
        print(f"  📚 Added: {book_data['title']} by {book_data['author']}")
        
        # Insert book text
        full_text = SAMPLE_TEXT * 5  # Repeat for length
        client.table("book_text").insert({
            "book_id": book_id,
            "content": full_text,
            "word_count": len(full_text.split())
        }).execute()
        
        # Insert chapters with calculated offsets
        chapter_length = len(full_text) // len(chapters)
        for i, chapter in enumerate(chapters):
            chapter_id = f"ch_{book_id}_{chapter['number']}"
            start_offset = i * chapter_length
            end_offset = (i + 1) * chapter_length if i < len(chapters) - 1 else len(full_text)
            
            client.table("chapters").insert({
                "id": chapter_id,
                "book_id": book_id,
                "number": chapter["number"],
                "title": chapter["title"],
                "start_offset": start_offset,
                "end_offset": end_offset
            }).execute()
        
        print(f"       ✓ Added {len(chapters)} chapters")
    
    print("\n✅ Seeding complete!")
    
    # Verify
    result = client.table("books").select("id, title, domain").execute()
    print(f"\n📊 Total books in database: {len(result.data)}")
    for book in result.data:
        print(f"   - {book['title']} ({book['domain']})")


def seed_sqlite():
    """Seed books into SQLite."""
    from app.db.database import get_db
    db = get_db()
    
    print("🌱 Seeding SQLite with sample books...")
    
    for book_data in SEED_BOOKS:
        book_id = book_data["id"]
        chapters = book_data.pop("chapters")
        
        # Check if book already exists
        existing = db.execute("SELECT id FROM books WHERE id = ?", (book_id,)).fetchone()
        if existing:
            print(f"  ⏭️  {book_data['title']} already exists, skipping")
            book_data["chapters"] = chapters  # Restore for next iteration
            continue
        
        # Insert book
        db.execute("""
            INSERT INTO books (id, title, author, domain, subdomain, is_public)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (book_id, book_data["title"], book_data["author"], 
              book_data["domain"], book_data.get("subdomain"), book_data["is_public"]))
        print(f"  📚 Added: {book_data['title']} by {book_data['author']}")
        
        # Insert book text
        full_text = SAMPLE_TEXT * 5
        db.execute("""
            INSERT INTO book_text (book_id, content, word_count)
            VALUES (?, ?, ?)
        """, (book_id, full_text, len(full_text.split())))
        
        # Insert chapters
        chapter_length = len(full_text) // len(chapters)
        for i, chapter in enumerate(chapters):
            chapter_id = f"ch_{book_id}_{chapter['number']}"
            start_offset = i * chapter_length
            end_offset = (i + 1) * chapter_length if i < len(chapters) - 1 else len(full_text)
            
            db.execute("""
                INSERT INTO chapters (id, book_id, number, title, start_offset, end_offset)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (chapter_id, book_id, chapter["number"], chapter["title"], start_offset, end_offset))
        
        book_data["chapters"] = chapters  # Restore
        print(f"       ✓ Added {len(chapters)} chapters")
    
    db.commit()
    print("\n✅ Seeding complete!")
    
    # Verify
    count = db.execute("SELECT COUNT(*) as c FROM books").fetchone()
    print(f"\n📊 Total books in database: {count['c']}")


def main():
    print("=" * 60)
    print("🏛️  ALEXANDRIA LIBRARY - Seed Books")
    print("=" * 60)
    
    # Initialize database connection
    init_db()
    
    if is_sqlite_mode():
        print("📁 Database: SQLite")
        seed_sqlite()
    else:
        print("☁️  Database: Supabase")
        seed_supabase()


if __name__ == "__main__":
    main()
