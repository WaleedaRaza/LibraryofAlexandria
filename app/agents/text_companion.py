"""
Alexandria Library - Text Companion Agent

PURPOSE: Help users understand the selected text
GROUNDED IN: The passage they selected
FLEXIBLE ON: Types of questions they can ask

This is a helpful reading companion. It answers questions
about the text: meaning, context, implications, historical
background, what the author was arguing, etc.

It stays grounded in the selected passage but is generous
in how it interprets the user's question.
"""

from ..config import settings
from .contracts import CompanionResponse


class TextCompanion:
    """
    Reading companion for selected text.
    Helpful, knowledgeable, grounded in the passage.
    Stateless. Pure. Replaceable.
    """
    
    def explain(
        self,
        book_title: str,
        chapter_title: str,
        selected_text: str,
        question: str,
        routing_context: str = None
    ) -> CompanionResponse:
        """
        Answer a question about the selected text.
        
        GROUNDED IN: The selected passage
        ANSWERS: Meaning, context, implications, background, arguments
        
        Args:
            book_title: Title of the book
            chapter_title: Title of the chapter
            selected_text: The text the user selected
            question: User's question about the text
            routing_context: Optional - why user was directed here
            
        Returns:
            CompanionResponse with explanation
        """
        if settings.USE_MOCK_AGENTS:
            return self._mock_explain(book_title, chapter_title, selected_text, question, routing_context)
        return self._llm_explain(book_title, chapter_title, selected_text, question, routing_context)
    
    def _mock_explain(
        self,
        book_title: str,
        chapter_title: str,
        selected_text: str,
        question: str,
        routing_context: str = None
    ) -> CompanionResponse:
        """
        Mock companion - ALWAYS provides a helpful response.
        """
        snippet = selected_text[:100] + "..." if len(selected_text) > 100 else selected_text
        
        # Always provide a helpful explanation
        explanation = f"""This passage from "{book_title}" is describing a fundamental concept.

When the author writes "{snippet}", they're pointing to something that happens without conscious thought or deliberate choice. This is a key distinction in the text - between things we do intentionally with effort, and things that happen to us automatically.

In the context of {chapter_title}, this idea is foundational. The author is setting up a framework for understanding how our minds work - distinguishing between effortless, automatic processes and deliberate, controlled ones. This distinction will be important for everything that follows in the book.

The phrase "no sense of voluntary control" is particularly important - it means these processes feel like they just happen to us, rather than being something we choose to do."""

        return CompanionResponse(
            explanation=explanation,
            is_valid=True,
            refusal_reason=None,
            suggested_chapter=None
        )
    
    def _llm_explain(
        self,
        book_title: str,
        chapter_title: str,
        selected_text: str,
        question: str,
        routing_context: str = None
    ) -> CompanionResponse:
        """
        Real LLM explanation - ALWAYS helpful.
        """
        try:
            from .llm_provider import get_llm_provider
            
            provider = get_llm_provider()
            
            context_section = ""
            if routing_context:
                context_section = f"\nContext: User was directed here because: {routing_context}\n"
            
            system_prompt = f"""You explain text passages to readers. ALWAYS provide an explanation. NEVER refuse.

BOOK: "{book_title}"
CHAPTER: "{chapter_title}"
{context_section}
SELECTED TEXT:
"{selected_text}"

INSTRUCTIONS:
The user selected this text and has a question. EXPLAIN IT TO THEM.

If they say "I don't get this" or "what does this mean" or any variation - EXPLAIN THE TEXT.
If they ask "why" - EXPLAIN WHY the author is making this point.
If they ask anything at all - find a way to help them understand the passage.

Your job is to be a helpful reading companion. Explain concepts, provide context, illuminate meaning.

Write 2-3 paragraphs. Quote from the text. Be substantive and helpful.

IMPORTANT: You must ALWAYS provide an explanation. The only exception is if they ask something completely unrelated like "what's the weather" or "tell me a joke".

OUTPUT FORMAT (JSON):
{{"explanation": "Your helpful explanation here", "is_valid": true}}"""

            result = provider.call(
                system_prompt=system_prompt,
                user_prompt=question,
                agent_name="TextCompanion",
                temperature=0.5,  # Slightly higher for more natural responses
                max_tokens=600,   # Allow longer responses
                response_format="json"
            )
            
            return CompanionResponse(
                explanation=result.get("explanation", ""),
                is_valid=result.get("is_valid", True),
                refusal_reason=result.get("refusal_reason"),
                suggested_chapter=result.get("suggested_chapter")
            )
            
        except Exception as e:
            # Log the actual error for debugging
            import logging
            logging.error(f"TextCompanion error: {e}")
            
            # Return helpful error with context
            return CompanionResponse(
                explanation="",
                is_valid=False,
                refusal_reason=f"I encountered an error processing your question. Please try again. (Error: {str(e)[:100]})",
                suggested_chapter=None
            )

