"""
Quick test script for OpenAI routing integration.

Usage:
    python test_routing.py                    # Test single query
    python test_routing.py "your question"    # Test specific question
"""

import sys
import os

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.agents.intent_classifier import IntentClassifier
from app.agents.reading_router import ReadingRouter
from app.agents.taxonomy import get_candidate_books, get_taxonomy_coverage
from app.services.canon_service import CanonService


def test_single_query(question: str):
    """Test routing for a single question."""
    print("=" * 80)
    print("ALEXANDRIA ROUTING TEST")
    print("=" * 80)
    print(f"\nQuestion: {question}")
    print("-" * 80)
    
    # Check mode
    use_mock = os.getenv("USE_MOCK_AGENTS", "true").lower() == "true"
    print(f"Mode: {'MOCK' if use_mock else 'LLM (OpenAI)'}")
    
    if not use_mock and not os.getenv("OPENAI_API_KEY"):
        print("\n❌ ERROR: OPENAI_API_KEY not set")
        print("Set it: export OPENAI_API_KEY='sk-...'")
        print("Or run in mock mode: export USE_MOCK_AGENTS=true")
        return
    
    # Initialize
    classifier = IntentClassifier()
    router = ReadingRouter()
    canon = CanonService()
    
    # Step 1: Classify
    print("\n1. INTENT CLASSIFICATION")
    print("-" * 80)
    intent = classifier.classify(question)
    print(f"Domain: {intent.domain}")
    print(f"Subdomain: {intent.subdomain or 'General'}")
    print(f"Confidence: {intent.confidence:.2%}")
    
    if not intent.is_valid:
        print(f"\n❌ REFUSED: {intent.refusal_reason}")
        return
    
    # Step 2: Taxonomy Gate
    print("\n2. TAXONOMY GATE")
    print("-" * 80)
    candidate_ids = get_candidate_books(intent.domain, intent.subdomain)
    print(f"Candidate books: {len(candidate_ids)}")
    for book_id in candidate_ids:
        print(f"  - {book_id}")
    
    if not candidate_ids:
        print("❌ No books in taxonomy for this domain")
        return
    
    # Step 3: Get books
    print("\n3. FETCH BOOKS")
    print("-" * 80)
    books = canon.get_books_by_domain(intent.domain)
    candidate_books = [b for b in books if b["id"] in candidate_ids]
    print(f"Available candidate books: {len(candidate_books)}")
    
    if not candidate_books:
        print("❌ No candidate books available")
        return
    
    # Step 4: Route
    print("\n4. ROUTING")
    print("-" * 80)
    chapters_by_book = {}
    for book in candidate_books[:10]:
        chapters_by_book[book["id"]] = canon.get_chapters(book["id"])
    
    routing = router.route(
        question=question,
        domain=intent.domain,
        subdomain=intent.subdomain,
        available_books=candidate_books,
        chapters_by_book=chapters_by_book
    )
    
    if not routing.is_valid:
        print(f"❌ ROUTING FAILED: {routing.refusal_reason}")
        return
    
    print(f"Paths returned: {len(routing.paths)}")
    print(f"Total recommendations: {routing.total_count}")
    
    for i, path in enumerate(routing.paths, 1):
        print(f"\n  Path {i}: {path.angle}")
        for rec in path.recommendations:
            print(f"    📖 {rec.book_title}")
            print(f"       Chapter {rec.chapter_number}: {rec.chapter_title}")
            print(f"       Rationale: {rec.rationale}")
    
    # Step 5: Stats
    if not use_mock:
        print("\n5. USAGE STATS")
        print("-" * 80)
        try:
            from app.agents.llm_provider import get_llm_provider
            provider = get_llm_provider()
            usage = provider.get_usage_summary()
            print(f"Total LLM calls: {usage['total_calls']}")
            print(f"Total tokens: {usage['total_tokens']}")
            for agent, stats in usage['by_agent'].items():
                print(f"  {agent}: {stats['total_tokens']} tokens")
        except Exception as e:
            print(f"Could not fetch usage: {e}")
    
    print("\n" + "=" * 80)
    print("✅ Test complete")
    print("=" * 80)


def show_taxonomy():
    """Show taxonomy coverage."""
    coverage = get_taxonomy_coverage()
    print("\nTAXONOMY COVERAGE:")
    print("-" * 80)
    print(f"Total mappings: {coverage['total_mappings']}")
    print(f"Unique books: {coverage['unique_books']}")
    print(f"Domains covered: {coverage['domains']}")
    print(f"Version: {coverage['version']}")
    print("\nMappings by domain:")
    for domain, count in coverage['mappings_by_domain'].items():
        print(f"  {domain}: {count} mappings")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
    else:
        question = "How do I deal with things I can't control?"
    
    test_single_query(question)
    show_taxonomy()

