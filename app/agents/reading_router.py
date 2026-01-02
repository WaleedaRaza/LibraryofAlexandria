"""
Alexandria Library - Reading Router Agent

PURPOSE: Choose WHERE to read from a pre-curated set
FORBIDDEN: summaries, conclusions, ideology

Given a domain and list of available books, this agent
selects specific chapters to read.

It does NOT summarize.
It does NOT draw conclusions.
It returns PARALLEL reading paths (different angles on the same question).
"""

from typing import List, Optional
from ..config import settings
from .contracts import RoutingResult, ReadingRecommendation, ReadingPath
from .llm_provider import get_llm_provider
from .routing_cache import get_routing_cache
from .domain_mapper import map_to_ids

# Use V1 taxonomy (synced with actual DB book IDs)
# V2 taxonomy (artifact-based) has stale book IDs that don't match DB
# TODO: Sync taxonomy_v2 artifacts when importing real 1300 book library
from .taxonomy import get_candidate_books, validate_book_id
USE_TAXONOMY_V2 = False


class ReadingRouter:
    """
    Routes questions to specific reading locations.
    Returns PARALLEL paths, not ranked recommendations.
    
    Stateless. Pure. Replaceable.
    """
    
    def route(
        self,
        question: str,
        domain: str,
        subdomain: Optional[str],
        available_books: List[dict],
        chapters_by_book: dict = None  # book_id -> list of chapter dicts
    ) -> RoutingResult:
        """
        Route a question to specific chapters via PARALLEL paths.
        
        Args:
            question: User's question
            domain: Classified domain
            subdomain: Classified subdomain (may be None)
            available_books: List of book dicts with id, title, author
            chapters_by_book: Dict mapping book_id to list of chapters
            
        Returns:
            RoutingResult with 2-4 parallel reading paths
        """
        # Check cache first
        if not settings.USE_MOCK_AGENTS:
            cache = get_routing_cache()
            cached_result = cache.get(question, domain, subdomain)
            if cached_result:
                return cached_result
        
        # Route
        if settings.USE_MOCK_AGENTS:
            result = self._mock_route(question, domain, subdomain, available_books, chapters_by_book or {})
        else:
            result = self._llm_route(question, domain, subdomain, available_books, chapters_by_book or {})
        
        # Cache result (only if valid)
        if not settings.USE_MOCK_AGENTS and result.is_valid:
            cache = get_routing_cache()
            cache.set(question, domain, subdomain, result)
        
        return result
    
    def _mock_route(
        self,
        question: str,
        domain: str,
        subdomain: Optional[str],
        available_books: List[dict],
        chapters_by_book: dict
    ) -> RoutingResult:
        """
        Mock router for development.
        Returns parallel paths with different angles.
        """
        if not available_books:
            return RoutingResult(
                paths=[],
                is_valid=True,
                refusal_reason="No books available in this domain."
            )
        
        paths = []
        
        # Path 1: Primary angle
        book1 = available_books[0]
        chapters1 = chapters_by_book.get(book1["id"], [])
        chapter1 = chapters1[0] if chapters1 else {"id": "ch_mock_1", "number": 1, "title": "Chapter 1"}
        
        paths.append(ReadingPath(
            angle="Foundational understanding",
            recommendations=[
                ReadingRecommendation(
                    book_id=book1["id"],
                    book_title=book1["title"],
                    book_author=book1["author"],
                    chapter_id=chapter1.get("id", "ch_mock_1"),
                    chapter_number=chapter1.get("number", 1),
                    chapter_title=chapter1.get("title", "Chapter 1"),
                    rationale=f"This text addresses the core concepts related to your question."
                )
            ]
        ))
        
        # Path 2: Alternative angle (if available)
        if len(available_books) > 1:
            book2 = available_books[1]
            chapters2 = chapters_by_book.get(book2["id"], [])
            chapter2 = chapters2[0] if chapters2 else {"id": "ch_mock_2", "number": 1, "title": "Chapter 1"}
            
            paths.append(ReadingPath(
                angle="Alternative perspective",
                recommendations=[
                    ReadingRecommendation(
                        book_id=book2["id"],
                        book_title=book2["title"],
                        book_author=book2["author"],
                        chapter_id=chapter2.get("id", "ch_mock_2"),
                        chapter_number=chapter2.get("number", 1),
                        chapter_title=chapter2.get("title", "Chapter 1"),
                        rationale=f"A different approach to the same question."
                    )
                ]
            ))
        
        return RoutingResult(
            paths=paths,
            is_valid=True
        )
    
    def _llm_route(
        self,
        question: str,
        domain: str,
        subdomain: Optional[str],
        available_books: List[dict],
        chapters_by_book: dict
    ) -> RoutingResult:
        """
        Real LLM routing with parallel paths.
        
        CONSTRAINTS:
        - Uses taxonomy gate to limit candidate books
        - Returns 2-4 paths (different angles)
        - Each path has 1-2 recommendations MAX
        - Total max 6 recommendations across all paths
        - Never hallucinate books/chapters not in candidates
        """
        try:
            # TAXONOMY GATE: Get candidate books
            if USE_TAXONOMY_V2:
                # Use artifact-based taxonomy
                gate = get_taxonomy_gate()
                domain_id, subdomain_id = map_to_ids(domain, subdomain)
                candidate_book_ids = gate.get_candidate_books(domain_id, subdomain_id, max_books=12)
                
                # Get candidate chapters from gate
                if candidate_book_ids:
                    candidate_chapters = gate.get_candidate_chapters(candidate_book_ids, max_chapters_per_book=8)
                    # Merge with existing chapters_by_book
                    for book_id, chapters in candidate_chapters.items():
                        if book_id not in chapters_by_book or not chapters_by_book[book_id]:
                            chapters_by_book[book_id] = chapters
            else:
                # Use hardcoded taxonomy (V1)
                candidate_book_ids = get_candidate_books(domain, subdomain, max_books=12)
            
            if not candidate_book_ids:
                return RoutingResult(
                    paths=[],
                    is_valid=False,
                    refusal_reason=f"No books mapped to {domain}/{subdomain or 'general'} in taxonomy"
                )
            
            # Filter available_books to only candidates
            candidate_books = [
                b for b in available_books 
                if b["id"] in candidate_book_ids
            ]
            
            if not candidate_books:
                return RoutingResult(
                    paths=[],
                    is_valid=False,
                    refusal_reason="No candidate books available"
                )
            
            # Format books and chapters for LLM
            books_info = []
            for b in candidate_books[:10]:  # Max 10 to keep prompt manageable
                chapters = chapters_by_book.get(b["id"], [])
                if chapters:
                    chapters_str = "\n    ".join([
                        f"Ch{c['number']}: {c['title']}" 
                        for c in chapters[:8]  # Max 8 chapters per book
                    ])
                else:
                    chapters_str = "Chapter 1: Full Text"
                
                books_info.append(
                    f"  {b['id']}:\n    \"{b['title']}\" by {b['author']}\n    Chapters:\n    {chapters_str}"
                )
            
            books_list = "\n\n".join(books_info)
            
            provider = get_llm_provider()
            
            system_prompt = f"""You select WHERE to read, not WHAT to conclude.

Given a user's question, you create 2-4 PARALLEL reading paths. Each path is a DIFFERENT SCHOOL OF THOUGHT or ANGLE on the question - not ranked alternatives, but genuinely different ways of approaching the problem.


QUESTION CONTEXT:

Domain: {domain}
Subdomain: {subdomain or 'General'}


CANDIDATE BOOKS (you MUST choose from this list, NO OTHER BOOKS):

{books_list}


WHAT MAKES A GOOD PATH:


GOOD ANGLES (genuinely different perspectives):
- "Power dynamics" vs "Structural forces" vs "Psychological patterns"
- "Ancient wisdom" vs "Modern analysis" vs "Practical application"
- "Individual agency" vs "Systemic factors" vs "Historical context"

BAD ANGLES (just different books, not different thinking):
- "Book 1" vs "Book 2" vs "Book 3"
- "First recommendation" vs "Second recommendation"
- "Primary source" vs "Secondary source"

The user should look at your paths and think: "These are genuinely different ways to understand my question."


RATIONALE WRITING:


GOOD rationale: "Machiavelli examines why leaders use fear as a tool - relevant to understanding workplace authority."
BAD rationale: "This book discusses leadership and power dynamics."

The rationale explains WHY this angle matters for THEIR question, not what the book is generally about.


OUTPUT FORMAT (strict JSON):

{{
  "paths": [
    {{
      "angle": "Power & hierarchy",
      "recommendations": [
        {{
          "book_id": "book_xxx",
          "chapter_number": 1,
          "rationale": "One sentence on why this angle matters for their question"
        }}
      ]
    }}
  ]
}}

═══════════════════════════════════════════════════════════════════
HARD RULES:
═══════════════════════════════════════════════════════════════════
1. Return 2-4 paths (never 1, never more than 4)
2. Each path has 1-2 recommendations MAX
3. Total max 6 recommendations across all paths
4. ONLY use book_ids from the candidate list above
5. ONLY use chapter numbers that exist for each book
6. If only one book is relevant, return 1 path (exception to rule 1)
7. NO summaries, NO conclusions, NO "the answer is..."
8. You point to sources. You do not interpret them.

RESPOND WITH ONLY VALID JSON. No markdown, no explanation."""

            result = provider.call(
                system_prompt=system_prompt,
                user_prompt=question,
                agent_name="ReadingRouter",
                temperature=0.3,
                max_tokens=600,
                response_format="json"
            )
            
            # Build paths from LLM response
            paths = []
            books_by_id = {b["id"]: b for b in candidate_books}
            path_count = 0
            total_recs = 0
            
            for path_data in result.get("paths", []):
                if path_count >= 4:  # Hard cap at 4 paths
                    break
                
                angle = path_data.get("angle", "Reading path")
                recommendations = []
                
                for rec in path_data.get("recommendations", []):
                    if total_recs >= 6:  # Hard cap at 6 total recommendations
                        break
                    
                    book_id = rec.get("book_id")
                    
                    # VALIDATION: Book must be in candidates
                    if not book_id or book_id not in books_by_id:
                        continue
                    
                    # VALIDATION: Book must be in taxonomy
                    if USE_TAXONOMY_V2:
                        gate = get_taxonomy_gate()
                        if not gate.validate_book_id(book_id):
                            continue
                    else:
                        if not validate_book_id(book_id):
                            continue
                    
                    book = books_by_id[book_id]
                    chapters = chapters_by_book.get(book_id, [])
                    ch_num = rec.get("chapter_number", 1)
                    
                    # Find chapter or create fallback
                    chapter = next(
                        (c for c in chapters if c.get("number") == ch_num),
                        None
                    )
                    
                    if not chapter and chapters:
                        # Chapter number doesn't exist, use first chapter
                        chapter = chapters[0]
                        ch_num = chapter.get("number", 1)
                    elif not chapter:
                        # No chapters at all, skip this recommendation
                        continue
                    
                    recommendations.append(
                        ReadingRecommendation(
                            book_id=book_id,
                            book_title=book["title"],
                            book_author=book["author"],
                            chapter_id=chapter.get("id", f"ch_{book_id}_{ch_num}"),
                            chapter_number=ch_num,
                            chapter_title=chapter.get("title", f"Chapter {ch_num}"),
                            rationale=rec.get("rationale", "Relevant to your question")[:200]  # Cap rationale length
                        )
                    )
                    total_recs += 1
                
                # Only add path if it has recommendations
                if recommendations:
                    paths.append(ReadingPath(
                        angle=angle[:100],  # Cap angle length
                        recommendations=recommendations
                    ))
                    path_count += 1
            
            # If LLM returned nothing useful, return refusal
            if not paths:
                return RoutingResult(
                    paths=[],
                    is_valid=False,
                    refusal_reason="Could not identify relevant reading for this question"
                )
            
            return RoutingResult(
                paths=paths,
                is_valid=True
            )
            
        except ValueError as e:
            # JSON parsing error
            return RoutingResult(
                paths=[],
                is_valid=False,
                refusal_reason="Error processing routing request"
            )
        except Exception as e:
            # Any other error - fail gracefully with mock result
            return self._mock_route(question, domain, subdomain, available_books, chapters_by_book)
