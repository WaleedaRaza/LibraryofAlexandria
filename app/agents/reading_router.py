"""
Alexandria Library - Reading Router Agent

PURPOSE: Route questions to the RIGHT sections using taxonomy data
INPUT:   question, domain, books, chapters (with summaries + themes)
OUTPUT:  Parallel reading paths pointing to specific sections

The taxonomy bridge:
  artifact JSON → sections with summaries/themes → this router → user reads the right passage

Mock mode uses keyword scoring against section themes + summaries.
LLM mode sends enriched section data in the prompt.
"""

import re
from typing import List, Optional, Dict, Set
from ..config import settings
from .contracts import RoutingResult, ReadingRecommendation, ReadingPath
from .llm_provider import get_llm_provider
from .routing_cache import get_routing_cache


class ReadingRouter:
    """Routes questions to specific reading locations using taxonomy data."""

    def route(
        self,
        question: str,
        domain: str,
        subdomain: Optional[str],
        available_books: List[dict],
        chapters_by_book: dict = None,
    ) -> RoutingResult:
        if not settings.USE_MOCK_AGENTS:
            cache = get_routing_cache()
            cached = cache.get(question, domain, subdomain)
            if cached:
                return cached

        if settings.USE_MOCK_AGENTS:
            result = self._mock_route(question, domain, subdomain, available_books, chapters_by_book or {})
        else:
            result = self._llm_route(question, domain, subdomain, available_books, chapters_by_book or {})

        if not settings.USE_MOCK_AGENTS and result.is_valid:
            cache = get_routing_cache()
            cache.set(question, domain, subdomain, result)

        return result

    # =========================================================================
    # MOCK ROUTER — taxonomy-driven section selection
    # =========================================================================

    def _mock_route(
        self,
        question: str,
        domain: str,
        subdomain: Optional[str],
        available_books: List[dict],
        chapters_by_book: dict,
    ) -> RoutingResult:
        """
        Intelligent mock router. Instead of blindly returning chapter[0],
        scores sections by keyword overlap between the question and each
        section's key_themes + summary.

        Flow:
          1. Extract keywords from question
          2. For each section, score = theme matches + summary matches
          3. Also boost sections referenced in the thematic_index
          4. Return top-scoring sections as reading paths
        """
        if not available_books:
            return RoutingResult(paths=[], is_valid=True, refusal_reason="No books in this domain.")

        # Extract question keywords (lowercased, stopwords removed)
        q_words = _extract_keywords(question)
        if not q_words:
            q_words = set(question.lower().split())

        paths = []

        for book in available_books[:3]:
            book_id = book["id"]
            chapters = chapters_by_book.get(book_id, [])
            if not chapters:
                continue

            # Load the thematic index for this book (theme → [section_ids])
            from ..services.artifact_loader import build_theme_to_sections
            theme_map = build_theme_to_sections(book_id)

            # Score every section
            scored: List[tuple] = []  # (score, chapter_dict)

            # Boost from thematic_index: if a question keyword appears in a theme name,
            # all sections mapped to that theme get a boost
            theme_boosted: Dict[str, float] = {}
            for theme_name, section_ids in theme_map.items():
                theme_words = set(theme_name.split())
                overlap = q_words & theme_words
                if overlap:
                    boost = len(overlap) * 3.0
                    for sid in section_ids:
                        theme_boosted[sid] = theme_boosted.get(sid, 0) + boost

            for ch in chapters:
                sid = ch.get("id", "")
                # Skip front/back matter and tiny sections
                if sid.startswith(("fm_", "bm_")):
                    continue
                size = ch.get("end_offset", 0) - ch.get("start_offset", 0)
                if size < 200:
                    continue

                score = 0.0

                # Score from key_themes
                themes = set(
                    t.lower().replace("_", " ")
                    for t in ch.get("key_themes", [])
                )
                for theme in themes:
                    theme_words = set(theme.split())
                    overlap = q_words & theme_words
                    score += len(overlap) * 2.0

                # Score from summary word overlap
                summary = ch.get("summary", "").lower()
                summary_words = set(re.findall(r'[a-z]+', summary))
                summary_overlap = q_words & summary_words
                score += len(summary_overlap) * 1.0

                # Score from title
                title_words = set(re.findall(r'[a-z]+', ch.get("title", "").lower()))
                title_overlap = q_words & title_words
                score += len(title_overlap) * 1.5

                # Thematic index boost
                score += theme_boosted.get(sid, 0)

                # Slight preference for longer sections (more content to read)
                if size > 3000:
                    score += 0.5

                if score > 0:
                    scored.append((score, ch))

            # Sort by score descending
            scored.sort(key=lambda x: x[0], reverse=True)

            if not scored:
                # No keyword match — fall back to first substantial section
                substantial = [
                    c for c in chapters
                    if not c.get("id", "").startswith(("fm_", "bm_"))
                    and (c.get("end_offset", 0) - c.get("start_offset", 0)) > 500
                ]
                if substantial:
                    scored = [(0.1, substantial[0])]

            if not scored:
                continue

            # Build paths from top results
            # Primary path: best match
            best_score, best_ch = scored[0]
            rationale = _build_rationale(best_ch, q_words)

            paths.append(ReadingPath(
                angle=_infer_angle(best_ch),
                recommendations=[
                    ReadingRecommendation(
                        book_id=book_id,
                        book_title=book["title"],
                        book_author=book["author"],
                        chapter_id=best_ch["id"],
                        chapter_number=best_ch["number"],
                        chapter_title=best_ch["title"],
                        rationale=rationale,
                    )
                ]
            ))

            # Secondary path: second best (if sufficiently different)
            if len(scored) > 1:
                second_score, second_ch = scored[1]
                if second_score > 0 and second_ch["id"] != best_ch["id"]:
                    rationale2 = _build_rationale(second_ch, q_words)
                    paths.append(ReadingPath(
                        angle=_infer_angle(second_ch),
                        recommendations=[
                            ReadingRecommendation(
                                book_id=book_id,
                                book_title=book["title"],
                                book_author=book["author"],
                                chapter_id=second_ch["id"],
                                chapter_number=second_ch["number"],
                                chapter_title=second_ch["title"],
                                rationale=rationale2,
                            )
                        ]
                    ))

        if not paths:
            return RoutingResult(paths=[], is_valid=True, refusal_reason="No relevant sections found.")

        return RoutingResult(paths=paths[:4], is_valid=True)

    # =========================================================================
    # LLM ROUTER — enriched prompt with summaries + themes
    # =========================================================================

    def _llm_route(
        self,
        question: str,
        domain: str,
        subdomain: Optional[str],
        available_books: List[dict],
        chapters_by_book: dict,
    ) -> RoutingResult:
        """
        LLM routing with enriched section data.
        The prompt includes section summaries and themes so the LLM
        can make informed decisions about where to send the reader.
        """
        try:
            candidate_books = available_books[:5]
            if not candidate_books:
                return RoutingResult(paths=[], is_valid=False, refusal_reason="No books available")

            # Format books with ENRICHED chapter data
            books_info = []
            for b in candidate_books:
                chapters = chapters_by_book.get(b["id"], [])
                # Filter to routable sections
                routable = [
                    c for c in chapters
                    if not c.get("id", "").startswith(("fm_", "bm_"))
                    and (c.get("end_offset", 0) - c.get("start_offset", 0)) > 200
                    and (c.get("key_themes") or c.get("summary"))
                ]

                if not routable:
                    continue

                # Format sections with summaries and themes
                sections_str = ""
                for c in routable[:30]:  # Cap to keep prompt manageable
                    themes = ", ".join(c.get("key_themes", []))
                    summary = c.get("summary", "")[:150]
                    sections_str += f"\n    Sec {c['number']} ({c['id']}): {c['title']}"
                    if themes:
                        sections_str += f"\n      Themes: {themes}"
                    if summary:
                        sections_str += f"\n      About: {summary}"

                books_info.append(
                    f"  {b['id']}:\n    \"{b['title']}\" by {b['author']}{sections_str}"
                )

            if not books_info:
                return RoutingResult(paths=[], is_valid=False, refusal_reason="No routable sections")

            books_list = "\n\n".join(books_info)

            provider = get_llm_provider()

            system_prompt = f"""You select WHERE to read. You have detailed section information including summaries and themes.

Use the summaries and themes to find the sections most relevant to the user's question. Do NOT default to the first section — find the RIGHT one.

QUESTION CONTEXT:
Domain: {domain}
Subdomain: {subdomain or 'General'}

CANDIDATE BOOKS AND SECTIONS:

{books_list}

OUTPUT FORMAT (strict JSON):

{{
  "paths": [
    {{
      "angle": "Short description of this reading angle",
      "recommendations": [
        {{
          "book_id": "book_xxx",
          "chapter_number": 5,
          "rationale": "Why THIS section answers their question (reference the themes/summary)"
        }}
      ]
    }}
  ]
}}

RULES:
1. Return 1-4 paths
2. Each path has 1-2 recommendations MAX
3. ONLY use book_ids and section numbers from the list above
4. Choose sections whose themes and summaries match the question
5. The rationale must explain why THIS section (not the book in general)
6. NEVER pick section 1 unless it genuinely matches best
7. NO summaries, NO conclusions — you point to sources

RESPOND WITH ONLY VALID JSON."""

            result = provider.call(
                system_prompt=system_prompt,
                user_prompt=question,
                agent_name="ReadingRouter",
                temperature=0.3,
                max_tokens=600,
                response_format="json"
            )

            # Build paths
            paths = []
            books_by_id = {b["id"]: b for b in candidate_books}

            for path_data in result.get("paths", [])[:4]:
                angle = path_data.get("angle", "Reading path")
                recommendations = []

                for rec in path_data.get("recommendations", [])[:2]:
                    book_id = rec.get("book_id")
                    if not book_id or book_id not in books_by_id:
                        continue

                    book = books_by_id[book_id]
                    chapters = chapters_by_book.get(book_id, [])
                    ch_num = rec.get("chapter_number", 1)

                    chapter = next((c for c in chapters if c.get("number") == ch_num), None)
                    if not chapter and chapters:
                        chapter = chapters[0]
                        ch_num = chapter.get("number", 1)
                    elif not chapter:
                        continue

                    recommendations.append(
                        ReadingRecommendation(
                            book_id=book_id,
                            book_title=book["title"],
                            book_author=book["author"],
                            chapter_id=chapter.get("id", f"sec_{ch_num:03d}"),
                            chapter_number=ch_num,
                            chapter_title=chapter.get("title", f"Section {ch_num}"),
                            rationale=rec.get("rationale", "Relevant to your question")[:200],
                        )
                    )

                if recommendations:
                    paths.append(ReadingPath(angle=angle[:100], recommendations=recommendations))

            if not paths:
                return self._mock_route(question, domain, subdomain, available_books, chapters_by_book)

            return RoutingResult(paths=paths, is_valid=True)

        except Exception:
            return self._mock_route(question, domain, subdomain, available_books, chapters_by_book)


# =============================================================================
# HELPERS
# =============================================================================

# Minimal stopwords — keeps domain-meaningful words like "being", "nature",
# "form", "cause", "truth", "substance" that are core philosophical concepts
_STOPWORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were",
    "have", "has", "had", "do", "does", "did",
    "will", "would", "could", "should", "may", "might", "can",
    "to", "of", "in", "for", "on", "with", "at", "by", "from", "as",
    "into", "through", "during", "before", "after",
    "between", "out", "off", "over", "under",
    "here", "there", "when", "where", "how",
    "all", "each", "every", "both", "few", "more", "most",
    "some", "such", "no", "not", "only", "so", "than", "too", "very",
    "just", "because", "but", "and", "or", "if", "while", "about",
    "what", "which", "who", "whom", "this", "that", "these", "those",
    "i", "me", "my", "we", "our", "you", "your", "he", "him", "his",
    "she", "her", "it", "its", "they", "them", "their",
})


def _extract_keywords(text: str) -> Set[str]:
    """Extract meaningful keywords from text, removing stopwords."""
    words = set(re.findall(r'[a-z]+', text.lower()))
    return words - _STOPWORDS


def _build_rationale(ch: dict, q_words: Set[str]) -> str:
    """Build a rationale string explaining why this section matches."""
    themes = ch.get("key_themes", [])
    summary = ch.get("summary", "")

    # Find which themes matched
    matched_themes = []
    for t in themes:
        t_words = set(t.lower().replace("_", " ").split())
        if t_words & q_words:
            matched_themes.append(t.replace("_", " "))

    if matched_themes:
        theme_str = ", ".join(matched_themes[:3])
        return f"This section addresses {theme_str} — directly relevant to your question."

    if summary:
        # Truncate summary to a useful snippet
        return summary[:180].rstrip() + ("..." if len(summary) > 180 else "")

    return "This section is relevant to your question."


def _infer_angle(ch: dict) -> str:
    """Infer a reading angle from section themes/title."""
    themes = ch.get("key_themes", [])
    if themes:
        return " & ".join(t.replace("_", " ").title() for t in themes[:2])
    title = ch.get("title", "")
    if title and len(title) > 3:
        return title
    return "Core concepts"
