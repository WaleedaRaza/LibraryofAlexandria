"""
Test harness for artifact-based taxonomy routing.

Validates that:
1. Routing returns valid JSON structure
2. Returns 2-4 parallel paths
3. Only uses candidate book/chapter IDs
4. Properly refuses when appropriate

Usage:
    python test_taxonomy_artifacts.py
"""

import sys
import os
from typing import Dict, Any, List

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.agents.intent_classifier import IntentClassifier
from app.agents.reading_router import ReadingRouter
from app.agents.domain_mapper import map_to_ids
from app.services.canon_service import CanonService

# Try to use V2 taxonomy
try:
    from app.agents.taxonomy_v2 import get_taxonomy_gate
    USE_V2 = True
except (FileNotFoundError, Exception) as e:
    print(f"⚠️  Could not load taxonomy V2: {e}")
    print("    Falling back to V1 (hardcoded)")
    USE_V2 = False


# Test queries (10 diverse questions)
TEST_QUERIES = [
    "How do I deal with things I can't control?",
    "Why does my boss act like that?",
    "How do I stop overthinking?",
    "What causes complex systems to fail?",
    "How do I gain influence at work?",
    "Why am I always anxious?",
    "What is strategic thinking?",
    "How do feedback loops work?",
    "What makes a good leader?",
    "How do I focus better?",
]


class RoutingValidator:
    """Validates routing outputs against constraints."""
    
    def __init__(self):
        self.classifier = IntentClassifier()
        self.router = ReadingRouter()
        self.canon = CanonService()
        
        if USE_V2:
            self.gate = get_taxonomy_gate()
            print(f"✓ Using taxonomy V2 (artifacts v{self.gate.get_artifact_version()})")
        else:
            self.gate = None
            print("✓ Using taxonomy V1 (hardcoded)")
    
    def validate_routing_result(
        self,
        routing,
        question: str,
        domain: str,
        subdomain: str,
        candidate_book_ids: List[str]
    ) -> Dict[str, Any]:
        """
        Validate a routing result against constraints.
        
        Returns validation report with pass/fail status.
        """
        report = {
            "query": question,
            "passed": True,
            "errors": [],
            "warnings": [],
            "info": {}
        }
        
        # Check 1: Valid structure
        if not hasattr(routing, 'paths'):
            report["errors"].append("Missing 'paths' attribute")
            report["passed"] = False
            return report
        
        # Check 2: 2-4 paths
        num_paths = len(routing.paths)
        report["info"]["num_paths"] = num_paths
        
        if num_paths < 2 or num_paths > 4:
            report["warnings"].append(f"Expected 2-4 paths, got {num_paths}")
        
        # Check 3: Each path has angle and recommendations
        for i, path in enumerate(routing.paths):
            if not path.angle:
                report["errors"].append(f"Path {i+1} missing angle")
                report["passed"] = False
            
            num_recs = len(path.recommendations)
            if num_recs < 1 or num_recs > 2:
                report["warnings"].append(f"Path {i+1} has {num_recs} recs (expected 1-2)")
        
        # Check 4: Total recommendations <= 6
        total_recs = routing.total_count
        report["info"]["total_recommendations"] = total_recs
        
        if total_recs > 6:
            report["errors"].append(f"Too many recommendations: {total_recs} > 6")
            report["passed"] = False
        
        # Check 5: All book_ids are in candidates
        for path in routing.paths:
            for rec in path.recommendations:
                if rec.book_id not in candidate_book_ids:
                    report["errors"].append(
                        f"Book {rec.book_id} not in candidates: {candidate_book_ids}"
                    )
                    report["passed"] = False
        
        # Check 6: All book_ids are valid in taxonomy
        if USE_V2 and self.gate:
            for path in routing.paths:
                for rec in path.recommendations:
                    if not self.gate.validate_book_id(rec.book_id):
                        report["errors"].append(
                            f"Book {rec.book_id} not valid in taxonomy"
                        )
                        report["passed"] = False
        
        return report
    
    def test_query(self, question: str) -> Dict[str, Any]:
        """Test a single query through the full pipeline."""
        result = {
            "query": question,
            "success": False,
            "intent": None,
            "routing": None,
            "validation": None
        }
        
        try:
            # Step 1: Classify
            intent = self.classifier.classify(question)
            result["intent"] = {
                "domain": intent.domain,
                "subdomain": intent.subdomain,
                "confidence": intent.confidence,
                "is_valid": intent.is_valid
            }
            
            if not intent.is_valid:
                result["refusal_reason"] = intent.refusal_reason
                result["success"] = True  # Valid refusal is success
                return result
            
            # Step 2: Get candidates
            if USE_V2 and self.gate:
                domain_id, subdomain_id = map_to_ids(intent.domain, intent.subdomain)
                candidate_book_ids = self.gate.get_candidate_books(
                    domain_id, subdomain_id, max_books=12
                )
            else:
                # Use DB query as fallback
                books = self.canon.get_books_by_domain(intent.domain)
                candidate_book_ids = [b["id"] for b in books]
            
            if not candidate_book_ids:
                result["refusal_reason"] = "No candidate books"
                result["success"] = True  # Valid refusal
                return result
            
            # Step 3: Get books and chapters
            books = self.canon.get_books_by_domain(intent.domain)
            candidate_books = [b for b in books if b["id"] in candidate_book_ids]
            
            chapters_by_book = {}
            for book in candidate_books[:10]:
                chapters_by_book[book["id"]] = self.canon.get_chapters(book["id"])
            
            # Step 4: Route
            routing = self.router.route(
                question=question,
                domain=intent.domain,
                subdomain=intent.subdomain,
                available_books=candidate_books,
                chapters_by_book=chapters_by_book
            )
            
            if not routing.is_valid:
                result["refusal_reason"] = routing.refusal_reason
                result["success"] = True  # Valid refusal
                return result
            
            result["routing"] = routing
            
            # Step 5: Validate
            validation = self.validate_routing_result(
                routing,
                question,
                intent.domain,
                intent.subdomain,
                candidate_book_ids
            )
            result["validation"] = validation
            result["success"] = validation["passed"]
            
        except Exception as e:
            result["error"] = str(e)
            result["success"] = False
        
        return result
    
    def run_all(self):
        """Run all test queries."""
        print("=" * 80)
        print("TAXONOMY ARTIFACT TEST HARNESS")
        print("=" * 80)
        print(f"Mode: {'LLM' if not os.getenv('USE_MOCK_AGENTS', 'true').lower() == 'true' else 'MOCK'}")
        print()
        
        results = []
        passed = 0
        failed = 0
        refused = 0
        
        for i, query in enumerate(TEST_QUERIES, 1):
            print(f"\n[{i}/{len(TEST_QUERIES)}] {query}")
            print("-" * 80)
            
            result = self.test_query(query)
            results.append(result)
            
            # Print intent
            if result.get("intent"):
                intent = result["intent"]
                print(f"Intent: {intent['domain']}/{intent['subdomain'] or 'General'}")
                print(f"Confidence: {intent['confidence']:.2%}")
            
            # Check for refusal
            if "refusal_reason" in result:
                print(f"✓ REFUSED: {result['refusal_reason']}")
                refused += 1
                continue
            
            # Print routing
            if result.get("routing"):
                routing = result["routing"]
                print(f"Paths: {len(routing.paths)}")
                for path in routing.paths:
                    print(f"  → {path.angle}")
                    for rec in path.recommendations:
                        print(f"     {rec.book_title} (Ch{rec.chapter_number})")
            
            # Print validation
            if result.get("validation"):
                validation = result["validation"]
                if validation["passed"]:
                    print(f"✓ VALIDATION PASSED")
                    print(f"   Paths: {validation['info']['num_paths']}")
                    print(f"   Recommendations: {validation['info']['total_recommendations']}")
                    passed += 1
                else:
                    print(f"✗ VALIDATION FAILED")
                    for error in validation["errors"]:
                        print(f"   ERROR: {error}")
                    for warning in validation["warnings"]:
                        print(f"   WARN: {warning}")
                    failed += 1
            
            if result.get("error"):
                print(f"✗ ERROR: {result['error']}")
                failed += 1
        
        # Summary
        print("\n\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"Total queries: {len(TEST_QUERIES)}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print(f"Refused: {refused}")
        print(f"Success rate: {(passed+refused)/len(TEST_QUERIES)*100:.1f}%")
        
        if USE_V2 and self.gate:
            print("\nTaxonomy Stats:")
            stats = self.gate.get_stats()
            print(f"  Artifact version: {stats['artifact_version']}")
            print(f"  Total books: {stats['total_books']}")
            print(f"  Total chapters: {stats['total_chapters']}")
            print(f"  Domains: {stats['total_domains']}")
        
        return failed == 0


def main():
    """Run the test harness."""
    validator = RoutingValidator()
    success = validator.run_all()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
