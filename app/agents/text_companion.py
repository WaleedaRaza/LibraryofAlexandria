"""
Alexandria Library - Text Companion Agent

PURPOSE: Help users understand the selected text
GROUNDED IN: The passage they selected
FLEXIBLE ON: Types of questions they can ask

Mock mode generates responses that actually reference the passage,
vary based on the question asked, and build on conversation history.
"""

from ..config import settings
from .contracts import CompanionResponse


class TextCompanion:
    """
    Reading companion for selected text.
    Helpful, knowledgeable, grounded in the passage.
    """

    def explain(
        self,
        book_title: str,
        chapter_title: str,
        selected_text: str,
        question: str,
        routing_context: str = None
    ) -> CompanionResponse:
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
        Mock companion that actually uses the inputs.
        Generates a response grounded in the selected text and question.
        """
        snippet = selected_text[:200].strip()
        if len(selected_text) > 200:
            snippet += "..."

        q_lower = question.lower()
        has_history = bool(routing_context and routing_context.strip())

        # Detect question type and respond accordingly
        if any(w in q_lower for w in ["what does", "what is", "meaning", "mean", "define", "definition"]):
            explanation = self._meaning_response(book_title, chapter_title, snippet, question, selected_text)
        elif any(w in q_lower for w in ["why", "reason", "purpose", "because"]):
            explanation = self._why_response(book_title, chapter_title, snippet, question, selected_text)
        elif any(w in q_lower for w in ["how", "method", "process", "way"]):
            explanation = self._how_response(book_title, chapter_title, snippet, question, selected_text)
        elif any(w in q_lower for w in ["agree", "disagree", "wrong", "right", "correct", "true", "false"]):
            explanation = self._evaluation_response(book_title, chapter_title, snippet, question, selected_text)
        elif any(w in q_lower for w in ["example", "instance", "illustrate", "apply"]):
            explanation = self._example_response(book_title, chapter_title, snippet, question, selected_text)
        elif any(w in q_lower for w in ["compare", "contrast", "differ", "similar", "relation"]):
            explanation = self._comparison_response(book_title, chapter_title, snippet, question, selected_text)
        else:
            explanation = self._general_response(book_title, chapter_title, snippet, question, selected_text)

        # If there's conversation history, acknowledge the thread
        if has_history:
            explanation = f"Building on our discussion — {explanation}"

        return CompanionResponse(
            explanation=explanation,
            is_valid=True,
            refusal_reason=None,
            suggested_chapter=None
        )

    # -----------------------------------------------------------------
    # Response generators by question type
    # -----------------------------------------------------------------

    def _meaning_response(self, book, chapter, snippet, question, full_text):
        # Extract a key phrase from the passage
        key = _extract_key_phrase(full_text)
        return (
            f'In this passage from {book} ({chapter}), {_first_person_author(book)} is working through '
            f'the concept of {key}. When the text states "{snippet}", it is making a claim about '
            f'the fundamental nature of this concept — not merely describing it, but defining how '
            f'it functions within the broader argument.\n\n'
            f'The key move here is the distinction being drawn. {_first_person_author(book)} is separating '
            f'what something IS (its essential nature) from how it APPEARS or is commonly understood. '
            f'This is characteristic of the method throughout {book} — stripping away surface '
            f'interpretations to reach the underlying structure of the concept.'
        )

    def _why_response(self, book, chapter, snippet, question, full_text):
        key = _extract_key_phrase(full_text)
        return (
            f'{_first_person_author(book)} makes this argument in {chapter} because it is essential '
            f'to the larger project of {book}. The passage "{snippet}" serves a specific function: '
            f'it establishes a premise that later arguments depend on.\n\n'
            f'Without this step — grounding the discussion of {key} — the subsequent reasoning '
            f'would lack foundation. The author is being methodical here: each claim builds on what '
            f'came before. This particular claim matters because it constrains what can be said '
            f'about {key} going forward. If you read on, you will see this premise being invoked '
            f'repeatedly.'
        )

    def _how_response(self, book, chapter, snippet, question, full_text):
        key = _extract_key_phrase(full_text)
        return (
            f'The method here is dialectical. In this passage from {chapter}, {_first_person_author(book)} '
            f'proceeds by first stating the common view, then examining it critically. When the text says '
            f'"{snippet}", this is part of that critical examination — testing whether the concept of '
            f'{key} holds up under scrutiny.\n\n'
            f'The process works like this: state a position, identify its implications, check whether '
            f'those implications are coherent. If they lead to contradiction, the position must be '
            f'revised. This is not just an abstract exercise — it is how {_first_person_author(book)} '
            f'arrives at conclusions throughout {book}.'
        )

    def _evaluation_response(self, book, chapter, snippet, question, full_text):
        key = _extract_key_phrase(full_text)
        return (
            f'Whether this argument succeeds depends on how you evaluate the premise. In "{snippet}", '
            f'{_first_person_author(book)} is making a substantive claim about {key} that not all '
            f'thinkers would accept.\n\n'
            f'The strength of the argument is its logical structure — the conclusion follows from '
            f'the premises. The vulnerability is whether you accept the starting point. Philosophers '
            f'after {_first_person_author(book)} have challenged exactly this assumption. But within '
            f'the framework of {book}, this claim is doing necessary work — it is not an idle '
            f'assertion but a load-bearing part of the larger argument.'
        )

    def _example_response(self, book, chapter, snippet, question, full_text):
        key = _extract_key_phrase(full_text)
        return (
            f'Consider what the passage "{snippet}" would look like applied concretely. '
            f'{_first_person_author(book)} is discussing {key} in abstract terms, but the principle '
            f'has tangible instances.\n\n'
            f'When the text distinguishes between different modes of {key}, think of how the same '
            f'distinction appears in everyday experience: the difference between knowing THAT '
            f'something is the case and knowing WHY it is the case. {_first_person_author(book)} '
            f'treats this as fundamental — not a mere academic distinction but something you can '
            f'observe in how people actually reason and act.'
        )

    def _comparison_response(self, book, chapter, snippet, question, full_text):
        key = _extract_key_phrase(full_text)
        return (
            f'The passage "{snippet}" sets up a distinction that runs through all of {book}. '
            f'{_first_person_author(book)} is drawing a line between two things that might seem '
            f'similar but are fundamentally different when it comes to {key}.\n\n'
            f'This comparison matters because collapsing the distinction leads to confusion — '
            f'something {_first_person_author(book)} accuses earlier thinkers of doing. The text '
            f'is not just cataloguing differences but showing why the difference MATTERS for '
            f'understanding {key} correctly.'
        )

    def _general_response(self, book, chapter, snippet, question, full_text):
        key = _extract_key_phrase(full_text)
        return (
            f'This passage from {book} ({chapter}) is addressing {key}. When {_first_person_author(book)} '
            f'writes "{snippet}", the text is making a point that connects to the broader argument '
            f'of this section.\n\n'
            f'The core idea here is that {key} is not what it first appears to be. '
            f'{_first_person_author(book)} is peeling back layers — moving from the obvious to the '
            f'underlying structure. Your question touches on exactly this: what is really being said '
            f'beneath the surface of these words. The answer lies in following the argument through: '
            f'each sentence in this passage constrains what the next one can claim.'
        )

    # -----------------------------------------------------------------
    # LLM mode
    # -----------------------------------------------------------------

    def _llm_explain(
        self,
        book_title: str,
        chapter_title: str,
        selected_text: str,
        question: str,
        routing_context: str = None
    ) -> CompanionResponse:
        try:
            from .llm_provider import get_llm_provider

            provider = get_llm_provider()

            context_section = ""
            if routing_context:
                context_section = f"\nPREVIOUS CONVERSATION:\n{routing_context}\n"

            system_prompt = f"""You are a reading companion for "{book_title}".

CHAPTER: "{chapter_title}"
{context_section}
SELECTED TEXT:
"{selected_text}"

The user selected this text and has a question. Your job:
1. EXPLAIN the passage — what it says, what it means, what the author is arguing
2. QUOTE from the selected text to ground your explanation
3. CONNECT to the broader argument of this chapter/book
4. If there is previous conversation, BUILD on it — don't repeat what was already said

Write 2-3 paragraphs. Be substantive. Reference the actual text.

OUTPUT FORMAT (JSON):
{{"explanation": "Your explanation here", "is_valid": true}}"""

            result = provider.call(
                system_prompt=system_prompt,
                user_prompt=question,
                agent_name="TextCompanion",
                temperature=0.5,
                max_tokens=600,
                response_format="json"
            )

            return CompanionResponse(
                explanation=result.get("explanation", ""),
                is_valid=result.get("is_valid", True),
                refusal_reason=result.get("refusal_reason"),
                suggested_chapter=result.get("suggested_chapter")
            )

        except Exception as e:
            import logging
            logging.error(f"TextCompanion error: {e}")
            return CompanionResponse(
                explanation="",
                is_valid=False,
                refusal_reason=f"Error processing your question. Please try again.",
                suggested_chapter=None
            )


# =============================================================================
# HELPERS
# =============================================================================

def _first_person_author(book_title: str) -> str:
    """Derive author reference from book title."""
    KNOWN = {
        "Metaphysics": "Aristotle",
        "The Republic": "Plato",
        "Meditations": "Marcus Aurelius",
        "The Art of War": "Sun Tzu",
        "The Prince": "Machiavelli",
    }
    return KNOWN.get(book_title, "the author")


def _extract_key_phrase(text: str) -> str:
    """Extract a likely key concept from the passage text."""
    import re
    # Look for philosophical terms
    CONCEPTS = [
        "substance", "being", "form", "matter", "cause", "essence",
        "potentiality", "actuality", "truth", "knowledge", "wisdom",
        "nature", "principle", "unity", "existence", "soul", "mind",
        "virtue", "justice", "power", "reason", "science", "art",
        "motion", "change", "time", "infinity", "number", "definition",
        "genus", "species", "category", "predication", "contradiction",
    ]

    text_lower = text.lower()
    found = []
    for c in CONCEPTS:
        count = text_lower.count(c)
        if count > 0:
            found.append((count, c))

    found.sort(reverse=True)
    if found:
        return found[0][1]

    # Fallback: use a noun-ish word from the first sentence
    words = re.findall(r'[a-z]{4,}', text_lower[:200])
    stopwords = {'this', 'that', 'with', 'from', 'have', 'been', 'were', 'they',
                 'their', 'about', 'which', 'when', 'there', 'will', 'each', 'make',
                 'like', 'other', 'than', 'them', 'then', 'what', 'some', 'also'}
    meaningful = [w for w in words if w not in stopwords]
    return meaningful[0] if meaningful else "the concept at hand"
