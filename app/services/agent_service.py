"""
Alexandria Library - Agent Service
Orchestrates the three agents. Enforces contracts.
Handles refusals centrally.

THE THREE AGENTS:
1. Intent Classifier - query → domain
2. Reading Router - domain → chapters
3. Text Companion - selected text → clarification

Agents are STATELESS. They don't touch the database.
This service coordinates them.
"""

from typing import List, Optional
from dataclasses import dataclass

from ..agents.contracts import (
    IntentResult,
    RoutingResult,
    CompanionResponse,
    ReadingRecommendation,
    ReadingPath
)
from ..agents.intent_classifier import IntentClassifier
from ..agents.reading_router import ReadingRouter
from ..agents.text_companion import TextCompanion
from .canon_service import CanonService


@dataclass
class QuestionRouting:
    """Full routing result for a user question."""
    question: str
    intent: IntentResult
    paths: List[ReadingPath]                    # Parallel reading paths
    recommendations: List[ReadingRecommendation] # Flattened (backward compat)
    message: str


class AgentService:
    """
    Orchestrates agents. This is the only place agents are called.
    
    Flow:
    1. User asks question
    2. Intent Classifier → domain/subdomain
    3. Reading Router → book + chapter recommendations
    4. Return structured result
    
    For section chat:
    1. User selects text, asks question
    2. Text Companion → constrained explanation
    3. Return response (or refusal if out of scope)
    """
    
    def __init__(self):
        self.intent_classifier = IntentClassifier()
        self.reading_router = ReadingRouter()
        self.text_companion = TextCompanion()
        self.canon = CanonService()
    
    def route_question(self, question: str) -> QuestionRouting:
        """
        Process a user question and route to relevant texts.
        
        This is the core flow: Ask → Route → Read
        Returns PARALLEL reading paths from ALL matched domains.
        
        For multi-domain questions (most questions), we route to each
        matched domain and aggregate the paths.
        """
        # Step 1: Classify intent (now returns 1-3 domain matches)
        intent = self.intent_classifier.classify(question)
        
        if not intent.is_valid:
            return QuestionRouting(
                question=question,
                intent=intent,
                paths=[],
                recommendations=[],
                message=intent.refusal_reason or "I couldn't understand your question."
            )
        
        # Step 2: For each matched domain, get books and route
        all_paths: List[ReadingPath] = []
        seen_book_ids = set()  # Dedupe across domains
        
        for match in intent.matches:
            # Get books for this domain
            books = self.canon.get_books_by_domain(match.domain)
            
            if not books:
                continue  # Skip this domain, try others
            
            # Get chapters for each book
            chapters_by_book = {}
            for book in books[:10]:
                if book["id"] not in seen_book_ids:
                    chapters_by_book[book["id"]] = self.canon.get_chapters(book["id"])
            
            if not chapters_by_book:
                continue  # No new books in this domain
            
            # Route within this domain
            routing = self.reading_router.route(
                question=question,
                domain=match.domain,
                subdomain=match.subdomain,
                available_books=books,
                chapters_by_book=chapters_by_book
            )
            
            # Add paths from this domain (label with domain for clarity)
            for path in routing.paths:
                # Mark book IDs as seen to avoid duplicates
                for rec in path.recommendations:
                    seen_book_ids.add(rec.book_id)
                all_paths.append(path)
        
        if not all_paths:
            domains_str = ", ".join([m.domain for m in intent.matches])
            return QuestionRouting(
                question=question,
                intent=intent,
                paths=[],
                recommendations=[],
                message=f"Found domains ({domains_str}) but no books available. You can request one."
            )
        
        # Flatten all recommendations for backward compatibility
        all_recommendations = [rec for path in all_paths for rec in path.recommendations]
        
        return QuestionRouting(
            question=question,
            intent=intent,
            paths=all_paths,
            recommendations=all_recommendations,
            message=""
        )
    
    def ask_text_companion(
        self,
        book_title: str,
        chapter_title: str,
        selected_text: str,
        question: str,
        routing_context: str = None
    ) -> CompanionResponse:
        """
        Ask the Text Companion about selected text.
        
        The companion is helpful and substantive, answering
        questions about meaning, context, implications, and
        the author's argument - all grounded in the selected text.
        
        Args:
            book_title: Title of the book
            chapter_title: Title of the chapter
            selected_text: The text the user selected
            question: User's question about the text
            routing_context: Optional - why user was directed here
        """
        return self.text_companion.explain(
            book_title=book_title,
            chapter_title=chapter_title,
            selected_text=selected_text,
            question=question,
            routing_context=routing_context
        )

