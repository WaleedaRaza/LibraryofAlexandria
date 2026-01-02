"""
Alexandria Library - Canon Service
Read-only access to books, chapters, and text.
Canon is SACRED. No mutations except by admin ingestion.

INVARIANTS:
- book_text.content is the single source of truth
- Chapters reference offsets, they don't store text
- file_path is internal only, never exposed to users
"""

from typing import Optional, List
from ..db.database import get_supabase, is_sqlite_mode


# =============================================================================
# MOCK BOOKS - For testing query→domain→books flow before real import
# These are returned when DB has no books for a domain
# =============================================================================
MOCK_BOOKS_BY_DOMAIN = {
    "Philosophy": [
        {"id": "mock_meditations", "title": "Meditations", "author": "Marcus Aurelius", "domain": "Philosophy", "subdomain": "Stoicism", "is_public": 1},
        {"id": "mock_nicomachean", "title": "Nicomachean Ethics", "author": "Aristotle", "domain": "Philosophy", "subdomain": "Ethics", "is_public": 1},
        {"id": "mock_republic", "title": "The Republic", "author": "Plato", "domain": "Philosophy", "subdomain": "Political Philosophy", "is_public": 1},
    ],
    "Strategy": [
        {"id": "mock_art_of_war", "title": "The Art of War", "author": "Sun Tzu", "domain": "Strategy", "subdomain": "Military Strategy", "is_public": 1},
        {"id": "mock_prince", "title": "The Prince", "author": "Niccolò Machiavelli", "domain": "Strategy", "subdomain": "Power Dynamics", "is_public": 1},
        {"id": "mock_48_laws", "title": "The 48 Laws of Power", "author": "Robert Greene", "domain": "Strategy", "subdomain": "Power Dynamics", "is_public": 1},
    ],
    "Psychology": [
        {"id": "mock_thinking_fast", "title": "Thinking, Fast and Slow", "author": "Daniel Kahneman", "domain": "Psychology", "subdomain": "Cognitive Science", "is_public": 1},
        {"id": "mock_influence", "title": "Influence", "author": "Robert Cialdini", "domain": "Psychology", "subdomain": "Social Psychology", "is_public": 1},
        {"id": "mock_righteous_mind", "title": "The Righteous Mind", "author": "Jonathan Haidt", "domain": "Psychology", "subdomain": "Moral Psychology", "is_public": 1},
    ],
    "Economics": [
        {"id": "mock_wealth_nations", "title": "The Wealth of Nations", "author": "Adam Smith", "domain": "Economics", "subdomain": "Political Economy", "is_public": 1},
        {"id": "mock_capital", "title": "Capital", "author": "Karl Marx", "domain": "Economics", "subdomain": "Political Economy", "is_public": 1},
    ],
    "Business": [
        {"id": "mock_zero_to_one", "title": "Zero to One", "author": "Peter Thiel", "domain": "Business", "subdomain": "Entrepreneurship", "is_public": 1},
        {"id": "mock_good_to_great", "title": "Good to Great", "author": "Jim Collins", "domain": "Business", "subdomain": "Management", "is_public": 1},
    ],
    "Technology": [
        {"id": "mock_mythical_man", "title": "The Mythical Man-Month", "author": "Fred Brooks", "domain": "Technology", "subdomain": "Software Engineering", "is_public": 1},
        {"id": "mock_thinking_systems", "title": "Thinking in Systems", "author": "Donella Meadows", "domain": "Technology", "subdomain": "Systems Design", "is_public": 1},
    ],
    "History": [
        {"id": "mock_decline_fall", "title": "The Decline and Fall of the Roman Empire", "author": "Edward Gibbon", "domain": "History", "subdomain": "Ancient History", "is_public": 1},
        {"id": "mock_guns_germs", "title": "Guns, Germs, and Steel", "author": "Jared Diamond", "domain": "History", "subdomain": "World History", "is_public": 1},
    ],
    "Politics": [
        {"id": "mock_leviathan", "title": "Leviathan", "author": "Thomas Hobbes", "domain": "Politics", "subdomain": "Political Theory", "is_public": 1},
        {"id": "mock_two_treatises", "title": "Two Treatises of Government", "author": "John Locke", "domain": "Politics", "subdomain": "Political Theory", "is_public": 1},
    ],
    "Religion": [
        {"id": "mock_varieties", "title": "The Varieties of Religious Experience", "author": "William James", "domain": "Religion", "subdomain": "Spirituality", "is_public": 1},
        {"id": "mock_tao_te_ching", "title": "Tao Te Ching", "author": "Lao Tzu", "domain": "Religion", "subdomain": "Eastern Philosophy", "is_public": 1},
    ],
    "Sociology": [
        {"id": "mock_protestant_ethic", "title": "The Protestant Ethic and the Spirit of Capitalism", "author": "Max Weber", "domain": "Sociology", "subdomain": "Social Theory", "is_public": 1},
    ],
    "Science": [
        {"id": "mock_origin_species", "title": "On the Origin of Species", "author": "Charles Darwin", "domain": "Science", "subdomain": "Evolution", "is_public": 1},
        {"id": "mock_structure_revolutions", "title": "The Structure of Scientific Revolutions", "author": "Thomas Kuhn", "domain": "Science", "subdomain": "Scientific Method", "is_public": 1},
    ],
    "Literature": [
        {"id": "mock_poetics", "title": "Poetics", "author": "Aristotle", "domain": "Literature", "subdomain": "Literary Criticism", "is_public": 1},
        {"id": "mock_hero_thousand", "title": "The Hero with a Thousand Faces", "author": "Joseph Campbell", "domain": "Literature", "subdomain": "Mythology", "is_public": 1},
    ],
    "Law": [
        {"id": "mock_spirit_laws", "title": "The Spirit of the Laws", "author": "Montesquieu", "domain": "Law", "subdomain": "Legal Theory", "is_public": 1},
    ],
    "Art": [
        {"id": "mock_art_spirit", "title": "The Art Spirit", "author": "Robert Henri", "domain": "Art", "subdomain": "Aesthetics", "is_public": 1},
    ],
    "Mathematics": [
        {"id": "mock_elements", "title": "Elements", "author": "Euclid", "domain": "Mathematics", "subdomain": "Geometry", "is_public": 1},
    ],
    "Medicine": [
        {"id": "mock_how_we_die", "title": "How We Die", "author": "Sherwin Nuland", "domain": "Medicine", "subdomain": "Mortality", "is_public": 1},
    ],
    "Communication": [
        {"id": "mock_rhetoric", "title": "Rhetoric", "author": "Aristotle", "domain": "Communication", "subdomain": "Rhetoric", "is_public": 1},
    ],
}

# Mock chapters for each mock book
MOCK_CHAPTERS = {
    "mock_meditations": [
        {"id": "ch_med_1", "book_id": "mock_meditations", "number": 1, "title": "Book I: Debts and Lessons", "start_offset": 0, "end_offset": 5000},
        {"id": "ch_med_2", "book_id": "mock_meditations", "number": 2, "title": "Book II: On the Frontier", "start_offset": 5000, "end_offset": 10000},
        {"id": "ch_med_3", "book_id": "mock_meditations", "number": 3, "title": "Book III: In Carnuntum", "start_offset": 10000, "end_offset": 15000},
    ],
    "mock_art_of_war": [
        {"id": "ch_aow_1", "book_id": "mock_art_of_war", "number": 1, "title": "Laying Plans", "start_offset": 0, "end_offset": 3000},
        {"id": "ch_aow_2", "book_id": "mock_art_of_war", "number": 2, "title": "Waging War", "start_offset": 3000, "end_offset": 6000},
        {"id": "ch_aow_3", "book_id": "mock_art_of_war", "number": 3, "title": "Attack by Stratagem", "start_offset": 6000, "end_offset": 9000},
    ],
    "mock_prince": [
        {"id": "ch_prince_1", "book_id": "mock_prince", "number": 1, "title": "How Many Kinds Of Principalities There Are", "start_offset": 0, "end_offset": 2000},
        {"id": "ch_prince_2", "book_id": "mock_prince", "number": 2, "title": "Concerning Hereditary Principalities", "start_offset": 2000, "end_offset": 4000},
        {"id": "ch_prince_3", "book_id": "mock_prince", "number": 3, "title": "Concerning Mixed Principalities", "start_offset": 4000, "end_offset": 8000},
    ],
    "mock_48_laws": [
        {"id": "ch_48_1", "book_id": "mock_48_laws", "number": 1, "title": "Never Outshine the Master", "start_offset": 0, "end_offset": 5000},
        {"id": "ch_48_2", "book_id": "mock_48_laws", "number": 2, "title": "Never Put Too Much Trust in Friends", "start_offset": 5000, "end_offset": 10000},
        {"id": "ch_48_3", "book_id": "mock_48_laws", "number": 3, "title": "Conceal Your Intentions", "start_offset": 10000, "end_offset": 15000},
    ],
    "mock_thinking_fast": [
        {"id": "ch_tf_1", "book_id": "mock_thinking_fast", "number": 1, "title": "The Characters of the Story", "start_offset": 0, "end_offset": 8000},
        {"id": "ch_tf_2", "book_id": "mock_thinking_fast", "number": 2, "title": "Attention and Effort", "start_offset": 8000, "end_offset": 16000},
    ],
    "mock_influence": [
        {"id": "ch_inf_1", "book_id": "mock_influence", "number": 1, "title": "Weapons of Influence", "start_offset": 0, "end_offset": 6000},
        {"id": "ch_inf_2", "book_id": "mock_influence", "number": 2, "title": "Reciprocation", "start_offset": 6000, "end_offset": 12000},
    ],
    "mock_righteous_mind": [
        {"id": "ch_rm_1", "book_id": "mock_righteous_mind", "number": 1, "title": "Where Does Morality Come From?", "start_offset": 0, "end_offset": 7000},
        {"id": "ch_rm_2", "book_id": "mock_righteous_mind", "number": 2, "title": "The Intuitive Dog and Its Rational Tail", "start_offset": 7000, "end_offset": 14000},
    ],
}

def _get_mock_chapters(book_id: str) -> List[dict]:
    """Get mock chapters for a book, with fallback generic chapters."""
    if book_id in MOCK_CHAPTERS:
        return MOCK_CHAPTERS[book_id]
    # Generic fallback chapters
    return [
        {"id": f"ch_{book_id}_1", "book_id": book_id, "number": 1, "title": "Introduction", "start_offset": 0, "end_offset": 5000},
        {"id": f"ch_{book_id}_2", "book_id": book_id, "number": 2, "title": "Core Concepts", "start_offset": 5000, "end_offset": 15000},
        {"id": f"ch_{book_id}_3", "book_id": book_id, "number": 3, "title": "Applications", "start_offset": 15000, "end_offset": 25000},
    ]


class CanonService:
    """
    Service for accessing canonical texts.
    Users read through this. It's read-only.
    """
    
    def get_books(
        self,
        domain: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 100
    ) -> List[dict]:
        """
        Get all public books, optionally filtered.
        
        Args:
            domain: Filter by domain (Philosophy, Strategy, etc.)
            search: Search in title/author
            limit: Max results
            
        Returns:
            List of book dicts (no file_path - that's internal)
        """
        if is_sqlite_mode():
            from ..db.database import get_db
            db = get_db()
            
            query = """
                SELECT id, title, author, domain, subdomain, is_public, created_at
                FROM books
                WHERE is_public = 1
            """
            params = []
            
            if domain:
                query += " AND domain = ?"
                params.append(domain)
            
            if search:
                query += " AND (title LIKE ? OR author LIKE ?)"
                search_term = f"%{search}%"
                params.extend([search_term, search_term])
            
            query += " ORDER BY title LIMIT ?"
            params.append(limit)
            
            rows = db.execute(query, params).fetchall()
            return [dict(row) for row in rows]
        
        # Supabase REST API
        client = get_supabase()
        query = client.table("books").select(
            "id, title, author, domain, subdomain, is_public, created_at"
        ).eq("is_public", 1)  # INTEGER column: 1=public, 0=private
        
        if domain:
            query = query.eq("domain", domain)
        
        if search:
            # Use ilike for case-insensitive search
            query = query.or_(f"title.ilike.%{search}%,author.ilike.%{search}%")
        
        result = query.order("title").limit(limit).execute()
        return result.data or []
    
    def get_book(self, book_id: str) -> Optional[dict]:
        """Get a single book by ID."""
        if is_sqlite_mode():
            from ..db.database import get_db
            db = get_db()
            row = db.execute(
                """
                SELECT id, title, author, domain, subdomain, is_public, created_at
                FROM books
                WHERE id = ? AND is_public = 1
                """,
                (book_id,)
            ).fetchone()
            return dict(row) if row else None
        
        # Supabase REST API
        client = get_supabase()
        result = client.table("books").select(
            "id, title, author, domain, subdomain, is_public, created_at"
        ).eq("id", book_id).eq("is_public", 1).execute()
        
        return result.data[0] if result.data else None
    
    def get_domains(self) -> List[str]:
        """Get list of unique domains for filtering."""
        if is_sqlite_mode():
            from ..db.database import get_db
            db = get_db()
            rows = db.execute(
                """
                SELECT DISTINCT domain
                FROM books
                WHERE domain IS NOT NULL AND is_public = 1
                ORDER BY domain
                """
            ).fetchall()
            return [row["domain"] for row in rows]
        
        # Supabase REST API
        client = get_supabase()
        result = client.table("books").select("domain").eq(
            "is_public", 1
        ).not_.is_("domain", "null").execute()
        
        # Get unique domains
        domains = sorted(set(row["domain"] for row in result.data or [] if row.get("domain")))
        return domains
    
    def get_book_count(self) -> int:
        """Get total count of public books."""
        if is_sqlite_mode():
            from ..db.database import get_db
            db = get_db()
            row = db.execute(
                "SELECT COUNT(*) as count FROM books WHERE is_public = 1"
            ).fetchone()
            return row["count"] if row else 0
        
        # Supabase REST API
        client = get_supabase()
        result = client.table("books").select(
            "id", count="exact"
        ).eq("is_public", 1).execute()
        
        return result.count if result.count else 0
    
    def get_chapter(self, chapter_id: str) -> Optional[dict]:
        """Get a single chapter by ID."""
        if is_sqlite_mode():
            from ..db.database import get_db
            db = get_db()
            row = db.execute(
                """
                SELECT id, book_id, number, title, start_offset, end_offset
                FROM chapters
                WHERE id = ?
                """,
                (chapter_id,)
            ).fetchone()
            return dict(row) if row else None
        
        # Supabase REST API
        client = get_supabase()
        result = client.table("chapters").select(
            "id, book_id, number, title, start_offset, end_offset"
        ).eq("id", chapter_id).execute()
        
        return result.data[0] if result.data else None
    
    def get_chapter_by_number(self, book_id: str, number: int) -> Optional[dict]:
        """Get chapter by book ID and chapter number."""
        if is_sqlite_mode():
            from ..db.database import get_db
            db = get_db()
            row = db.execute(
                """
                SELECT id, book_id, number, title, start_offset, end_offset
                FROM chapters
                WHERE book_id = ? AND number = ?
                """,
                (book_id, number)
            ).fetchone()
            return dict(row) if row else None
        
        # Supabase REST API
        client = get_supabase()
        result = client.table("chapters").select(
            "id, book_id, number, title, start_offset, end_offset"
        ).eq("book_id", book_id).eq("number", number).execute()
        
        return result.data[0] if result.data else None
    
    def get_chapter_text(self, book_id: str, chapter_id: str) -> str:
        """
        Get the text for a specific chapter.
        
        This extracts text from book_text.content using chapter offsets.
        The chapter table stores offsets, not text - this is by design.
        """
        if is_sqlite_mode():
            from ..db.database import get_db
            db = get_db()
            row = db.execute(
                """
                SELECT bt.content, c.start_offset, c.end_offset
                FROM book_text bt
                JOIN chapters c ON c.book_id = bt.book_id
                WHERE bt.book_id = ? AND c.id = ?
                """,
                (book_id, chapter_id)
            ).fetchone()
            
            if not row:
                return ""
            
            content = row["content"]
            start = row["start_offset"]
            end = row["end_offset"]
            return content[start:end]
        
        # Supabase REST API - need two queries (no JOINs with text slicing)
        client = get_supabase()
        
        # Get chapter offsets
        chapter_result = client.table("chapters").select(
            "start_offset, end_offset"
        ).eq("id", chapter_id).eq("book_id", book_id).execute()
        
        if not chapter_result.data:
            return ""
        
        chapter = chapter_result.data[0]
        start = chapter["start_offset"]
        end = chapter["end_offset"]
        
        # Get book text
        text_result = client.table("book_text").select("content").eq("book_id", book_id).execute()
        
        if not text_result.data:
            return ""
        
        content = text_result.data[0]["content"]
        return content[start:end]
    
    def get_full_text(self, book_id: str) -> str:
        """
        Get the full text of a book.
        Admin use only - prefer get_chapter_text for reading.
        """
        if is_sqlite_mode():
            from ..db.database import get_db
            db = get_db()
            row = db.execute(
                "SELECT content FROM book_text WHERE book_id = ?",
                (book_id,)
            ).fetchone()
            return row["content"] if row else ""
        
        # Supabase REST API
        client = get_supabase()
        result = client.table("book_text").select("content").eq("book_id", book_id).execute()
        
        return result.data[0]["content"] if result.data else ""
    
    def get_books_by_domain(self, domain: str) -> List[dict]:
        """
        Get all books in a specific domain.
        
        Falls back to mock books if DB returns empty - this allows
        testing the full query→domain→books pipeline before importing
        real books.
        """
        books = self.get_books(domain=domain)
        
        # Fallback to mock books if DB is empty for this domain
        if not books and domain in MOCK_BOOKS_BY_DOMAIN:
            return MOCK_BOOKS_BY_DOMAIN[domain]
        
        return books
    
    def get_chapters(self, book_id: str) -> List[dict]:
        """Get all chapters for a book."""
        # Check if this is a mock book first
        if book_id.startswith("mock_"):
            return _get_mock_chapters(book_id)
        
        if is_sqlite_mode():
            from ..db.database import get_db
            db = get_db()
            rows = db.execute(
                """
                SELECT id, book_id, number, title, start_offset, end_offset
                FROM chapters
                WHERE book_id = ?
                ORDER BY number
                """,
                (book_id,)
            ).fetchall()
            return [dict(row) for row in rows]
        
        # Supabase REST API
        client = get_supabase()
        result = client.table("chapters").select(
            "id, book_id, number, title, start_offset, end_offset"
        ).eq("book_id", book_id).order("number").execute()
        
        return result.data or []
    
    def search_books(self, query: str) -> List[dict]:
        """Search books by title or author."""
        return self.get_books(search=query)
