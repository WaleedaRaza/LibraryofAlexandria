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
        Mock companion for development.
        Provides helpful, substantive mock responses.
        """
        question_lower = question.lower()
        snippet = selected_text[:100] + "..." if len(selected_text) > 100 else selected_text
        
        # Detect question type and provide appropriate mock response
        if any(w in question_lower for w in ["what does", "what is", "meaning", "mean"]):
            explanation = f"""In this passage, the author is making a key argument about the nature of their subject. 

The phrase "{snippet}" captures a central idea: that understanding requires moving beyond surface appearances. 

The author is building on earlier arguments in {chapter_title} to show how this concept connects to their broader thesis in "{book_title}". They're suggesting that the reader should pay attention to underlying structures rather than immediate impressions."""

        elif any(w in question_lower for w in ["why", "reason", "because"]):
            explanation = f"""The author makes this argument for several interconnected reasons.

First, they're responding to a common misconception - that things are as they appear. The passage "{snippet}" challenges this by introducing a more nuanced framework.

Second, this connects to the author's broader project in "{book_title}". They're trying to give readers tools for seeing through appearances to underlying dynamics.

The context of {chapter_title} is important here: the author has been building toward this point throughout."""

        elif any(w in question_lower for w in ["how", "works", "function"]):
            explanation = f"""The author describes a mechanism here that's central to their argument.

In "{snippet}", they're showing how this process operates in practice. The key insight is that it's not a single cause-and-effect, but a system of interconnected elements.

This is typical of the author's approach in "{book_title}" - they avoid simple explanations in favor of showing how multiple factors interact. {chapter_title} demonstrates this analytical method clearly."""

        elif any(w in question_lower for w in ["important", "significance", "matters"]):
            explanation = f"""This passage is significant for understanding the author's central argument.

"{snippet}" represents a turning point where the author moves from describing a problem to proposing their framework for understanding it.

Within "{book_title}", this chapter establishes the foundation for everything that follows. The author is giving readers the conceptual tools they'll need for the rest of the work."""

        else:
            # Generic but still helpful response
            explanation = f"""This passage from "{book_title}" addresses a key theme in the author's work.

The text "{snippet}" illustrates the author's analytical approach. They're not just making an observation but building toward a larger argument about how we should understand their subject.

{chapter_title} is strategically placed in the work to establish these concepts before the author develops their full argument. The author's style here - careful, methodical, building on each point - is characteristic of their broader approach."""

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
        Real LLM explanation - helpful and grounded.
        """
        try:
            from .llm_provider import get_llm_provider
            
            provider = get_llm_provider()
            
            context_section = ""
            if routing_context:
                context_section = f"""
WHY THE USER IS HERE:
{routing_context}

This context helps you understand what they're trying to learn.
"""
            
            system_prompt = f"""You are a knowledgeable reading companion. You help users understand texts they're reading.

═══════════════════════════════════════════════════════════════════
BOOK CONTEXT
═══════════════════════════════════════════════════════════════════
Book: "{book_title}"
Chapter: "{chapter_title}"
{context_section}
═══════════════════════════════════════════════════════════════════
SELECTED PASSAGE
═══════════════════════════════════════════════════════════════════
\"\"\"{selected_text}\"\"\"

═══════════════════════════════════════════════════════════════════
YOUR ROLE
═══════════════════════════════════════════════════════════════════
You help the reader understand this passage. You can:
- Explain what the author means
- Provide historical or philosophical context
- Clarify difficult language or concepts
- Discuss the author's argument and reasoning
- Explain why this matters in the context of the book
- Answer "what does this mean for X" questions by explaining the author's perspective

Stay GROUNDED in the selected passage, but be HELPFUL and SUBSTANTIVE.
Don't just define words - illuminate the author's thinking.

═══════════════════════════════════════════════════════════════════
RESPONSE STYLE
═══════════════════════════════════════════════════════════════════
- Quote directly from the passage to anchor your explanation
- Provide context that helps the reader understand
- Be substantive - give them real insight, not platitudes
- Write 2-4 paragraphs, not one-liners
- Sound like a thoughtful professor, not a chatbot

═══════════════════════════════════════════════════════════════════
ONLY REFUSE IF:
═══════════════════════════════════════════════════════════════════
- The question has NOTHING to do with the text (e.g., "What's the weather?")
- They're asking about a completely different book

For everything else, find a way to be helpful.

═══════════════════════════════════════════════════════════════════
OUTPUT FORMAT (JSON only)
═══════════════════════════════════════════════════════════════════
{{"explanation": "Your helpful, substantive response", "is_valid": true}}

Or if you truly can't help:
{{"is_valid": false, "refusal_reason": "Brief reason"}}"""

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

