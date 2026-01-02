"""
Alexandria Library - Eval Harness
Tests routing agents with sample queries.

Run this to inspect routing quality before unmocking.
Prints routing outputs for manual review.

Usage:
    python -m app.agents.eval_harness
"""

import sys
from typing import List, Dict, Any
from dataclasses import dataclass

from .intent_classifier import IntentClassifier
from .reading_router import ReadingRouter
from .llm_provider import get_llm_provider
from ..services.canon_service import CanonService


@dataclass
class TestQuery:
    """A test query with expected behavior notes."""
    query: str
    expected_domain: str
    notes: str = ""


# =============================================================================
# TEST QUERIES
# 30 diverse questions across domains
# =============================================================================

TEST_QUERIES: List[TestQuery] = [
    # Philosophy / Stoicism
    TestQuery(
        query="How do I deal with things I can't control?",
        expected_domain="Philosophy",
        notes="Should route to Meditations"
    ),
    TestQuery(
        query="Why does suffering happen?",
        expected_domain="Philosophy",
        notes="Stoic perspective"
    ),
    TestQuery(
        query="What is virtue?",
        expected_domain="Philosophy",
        notes="Core philosophy question"
    ),
    TestQuery(
        query="How do I find meaning in life?",
        expected_domain="Philosophy",
        notes="Existential"
    ),
    
    # Strategy / Power
    TestQuery(
        query="Why does my boss act like that?",
        expected_domain="Strategy",
        notes="Should consider 48 Laws of Power"
    ),
    TestQuery(
        query="How do I gain influence at work?",
        expected_domain="Strategy",
        notes="Power dynamics"
    ),
    TestQuery(
        query="Why do people manipulate others?",
        expected_domain="Strategy",
        notes="Political psychology"
    ),
    TestQuery(
        query="What makes a good leader?",
        expected_domain="Strategy",
        notes="Leadership principles"
    ),
    
    # Strategy / War
    TestQuery(
        query="How do I handle conflict with someone?",
        expected_domain="Strategy",
        notes="Should route to Art of War"
    ),
    TestQuery(
        query="What is strategic thinking?",
        expected_domain="Strategy",
        notes="Core strategy question"
    ),
    TestQuery(
        query="How do I win an argument?",
        expected_domain="Strategy",
        notes="Tactical approach"
    ),
    
    # Psychology / Mindfulness
    TestQuery(
        query="How do I stop overthinking?",
        expected_domain="Psychology",
        notes="Should route to mindfulness"
    ),
    TestQuery(
        query="Why am I always anxious?",
        expected_domain="Psychology",
        notes="Mental state"
    ),
    TestQuery(
        query="How do I focus better?",
        expected_domain="Psychology",
        notes="Attention and presence"
    ),
    TestQuery(
        query="What is mindfulness?",
        expected_domain="Psychology",
        notes="Core concept"
    ),
    
    # Psychology / Cognition
    TestQuery(
        query="Why do I make bad decisions?",
        expected_domain="Psychology",
        notes="Decision making, cognitive bias"
    ),
    TestQuery(
        query="How does bias affect thinking?",
        expected_domain="Psychology",
        notes="Cognitive science"
    ),
    TestQuery(
        query="Why do people believe what they believe?",
        expected_domain="Psychology",
        notes="Belief formation"
    ),
    
    # Technology / Systems
    TestQuery(
        query="Why are systems so complex?",
        expected_domain="Technology",
        notes="Should route to Thinking in Systems"
    ),
    TestQuery(
        query="How do feedback loops work?",
        expected_domain="Technology",
        notes="Systems thinking"
    ),
    TestQuery(
        query="Why do organizations fail?",
        expected_domain="Technology",
        notes="Could be systems or strategy"
    ),
    TestQuery(
        query="What causes unintended consequences?",
        expected_domain="Technology",
        notes="Systems behavior"
    ),
    
    # Business / Economics
    TestQuery(
        query="Why do markets crash?",
        expected_domain="Economics",
        notes="Economic systems"
    ),
    TestQuery(
        query="How does capitalism work?",
        expected_domain="Economics",
        notes="Economic systems"
    ),
    TestQuery(
        query="Why do companies fail?",
        expected_domain="Business",
        notes="Business strategy"
    ),
    
    # Edge cases / Multi-domain
    TestQuery(
        query="Why do power dynamics ruin relationships?",
        expected_domain="Strategy",
        notes="Could be Strategy or Psychology"
    ),
    TestQuery(
        query="How do I stop caring what people think?",
        expected_domain="Philosophy",
        notes="Could be Philosophy or Psychology"
    ),
    TestQuery(
        query="Why do smart people believe stupid things?",
        expected_domain="Psychology",
        notes="Cognitive bias / social psychology"
    ),
    TestQuery(
        query="Frustrated at work",
        expected_domain="Strategy",
        notes="Vague but work-related"
    ),
    TestQuery(
        query="Confused about money",
        expected_domain="Economics",
        notes="Vague but economic"
    ),
    
    # Should refuse or struggle
    TestQuery(
        query="What's the weather today?",
        expected_domain="N/A",
        notes="Should refuse - not in scope"
    ),
]


# =============================================================================
# EVAL RUNNER
# =============================================================================

class EvalRunner:
    """Runs evaluation queries and prints results."""
    
    def __init__(self, use_mock: bool = False):
        self.use_mock = use_mock
        self.classifier = IntentClassifier()
        self.router = ReadingRouter()
        self.canon = CanonService()
    
    def run_query(self, test: TestQuery) -> Dict[str, Any]:
        """Run a single test query through the routing pipeline."""
        # Step 1: Classify intent (now returns 1-3 domain matches)
        intent = self.classifier.classify(test.query)
        
        # Step 2: Route using primary domain (for eval simplicity)
        routing = None
        if intent.is_valid and intent.matches:
            primary = intent.matches[0]
            books = self.canon.get_books_by_domain(primary.domain)
            chapters_by_book = {}
            for book in books[:10]:
                chapters_by_book[book["id"]] = self.canon.get_chapters(book["id"])
            
            # Step 3: Route
            routing = self.router.route(
                question=test.query,
                domain=primary.domain,
                subdomain=primary.subdomain,
                available_books=books,
                chapters_by_book=chapters_by_book
            )
        
        return {
            "query": test.query,
            "expected_domain": test.expected_domain,
            "notes": test.notes,
            "intent": intent,
            "routing": routing,
            "all_domains": [m.domain for m in intent.matches] if intent.is_valid else []
        }
    
    def run_all(self):
        """Run all test queries and print results."""
        print("=" * 80)
        print("ALEXANDRIA ROUTING EVAL")
        print(f"Mode: {'MOCK' if self.use_mock else 'LLM'}")
        print("=" * 80)
        print()
        
        results = []
        for i, test in enumerate(TEST_QUERIES, 1):
            print(f"\n[{i}/{len(TEST_QUERIES)}] {test.query}")
            print("-" * 80)
            
            try:
                result = self.run_query(test)
                results.append(result)
                
                # Print intent
                intent = result["intent"]
                print(f"Intent: {intent.domain}/{intent.subdomain or 'General'}")
                print(f"Confidence: {intent.confidence:.2f}")
                
                if not intent.is_valid:
                    print(f"REFUSED: {intent.refusal_reason}")
                    continue
                
                # Print routing
                routing = result["routing"]
                if routing and routing.is_valid:
                    print(f"Paths: {len(routing.paths)}")
                    for path in routing.paths:
                        print(f"\n  Angle: {path.angle}")
                        for rec in path.recommendations:
                            print(f"    → {rec.book_title} (Ch{rec.chapter_number}: {rec.chapter_title})")
                            print(f"      Rationale: {rec.rationale}")
                else:
                    print(f"ROUTING FAILED: {routing.refusal_reason if routing else 'No routing'}")
                
                # Check if domain matches expected
                if intent.domain != test.expected_domain and test.expected_domain != "N/A":
                    print(f"\n⚠️  Expected {test.expected_domain}, got {intent.domain}")
                
            except Exception as e:
                print(f"ERROR: {str(e)}")
                results.append(None)
        
        # Print summary
        print("\n\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        
        valid_results = [r for r in results if r is not None]
        successful = [r for r in valid_results if r["intent"].is_valid]
        routed = [r for r in successful if r["routing"] and r["routing"].is_valid]
        
        print(f"Total queries: {len(TEST_QUERIES)}")
        print(f"Completed: {len(valid_results)}")
        print(f"Valid intent: {len(successful)}")
        print(f"Successfully routed: {len(routed)}")
        print(f"Success rate: {len(routed)/len(TEST_QUERIES)*100:.1f}%")
        
        # Domain breakdown
        print("\nDomain breakdown:")
        domain_counts = {}
        for r in successful:
            domain = r["intent"].domain
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
        for domain, count in sorted(domain_counts.items(), key=lambda x: -x[1]):
            print(f"  {domain}: {count}")
        
        # Usage stats (if using LLM)
        if not self.use_mock:
            try:
                provider = get_llm_provider()
                usage = provider.get_usage_summary()
                print(f"\nLLM Usage:")
                print(f"  Total calls: {usage['total_calls']}")
                print(f"  Total tokens: {usage['total_tokens']}")
                print(f"  By agent:")
                for agent, stats in usage['by_agent'].items():
                    print(f"    {agent}: {stats['calls']} calls, {stats['total_tokens']} tokens")
            except:
                pass


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

def main():
    """Run the eval harness."""
    import os
    
    # Check if we should use mock or real LLM
    use_mock = os.getenv("USE_MOCK_AGENTS", "true").lower() == "true"
    
    if not use_mock and not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY not set. Set it or run with USE_MOCK_AGENTS=true")
        sys.exit(1)
    
    runner = EvalRunner(use_mock=use_mock)
    runner.run_all()


if __name__ == "__main__":
    main()

