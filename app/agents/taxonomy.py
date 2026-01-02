"""
Alexandria Library - Taxonomy Gate
Maps domains/subdomains to candidate book_ids.

This is the constraint that keeps the router grounded.
It CANNOT recommend books that aren't in the taxonomy.

INVARIANT: All book_ids must exist in the books table.
MAINTENANCE: Update when new books are added to match their domain/subdomain.
"""

from typing import List, Set, Optional
from dataclasses import dataclass


@dataclass
class TaxonomyMapping:
    """Maps a domain (and optional subdomain) to book IDs."""
    domain: str
    subdomain: Optional[str]
    book_ids: List[str]
    version: int = 1  # Increment when taxonomy changes (for cache invalidation)


# =============================================================================
# TAXONOMY VERSION
# Increment this when you change the mappings below (invalidates routing cache)
# =============================================================================
TAXONOMY_VERSION = 3  # V3: Synced with actual DB book IDs + mock fallbacks


# =============================================================================
# DOMAIN → BOOK_IDS MAPPINGS
# 
# These are HARDCODED for now. In production, this should come from:
# - books table with domain/subdomain fields
# - OR a separate taxonomy table
# - OR a config file
#
# For V1: Hardcode based on actual books in DB
# =============================================================================

TAXONOMY: List[TaxonomyMapping] = [
    # ==========================================================================
    # PHILOSOPHY - Real books: book_meditations, book_enchiridion, book_republic
    # ==========================================================================
    TaxonomyMapping(
        domain="Philosophy",
        subdomain="Stoicism",
        book_ids=["book_meditations", "book_enchiridion", "mock_meditations"]
    ),
    TaxonomyMapping(
        domain="Philosophy",
        subdomain="Ethics",
        book_ids=["book_enchiridion", "mock_nicomachean"]
    ),
    TaxonomyMapping(
        domain="Philosophy",
        subdomain="Political Philosophy",
        book_ids=["book_republic", "mock_republic"]
    ),
    TaxonomyMapping(
        domain="Philosophy",
        subdomain=None,
        book_ids=["book_meditations", "book_enchiridion", "book_republic", "mock_meditations", "mock_nicomachean", "mock_republic"]
    ),
    
    # ==========================================================================
    # STRATEGY - Real books: book_art_of_war, book_prince
    # ==========================================================================
    TaxonomyMapping(
        domain="Strategy",
        subdomain="Military Strategy",
        book_ids=["book_art_of_war", "mock_art_of_war"]
    ),
    TaxonomyMapping(
        domain="Strategy",
        subdomain="Power Dynamics",
        book_ids=["book_prince", "mock_prince", "mock_48_laws"]
    ),
    TaxonomyMapping(
        domain="Strategy",
        subdomain=None,
        book_ids=["book_art_of_war", "book_prince", "mock_art_of_war", "mock_prince", "mock_48_laws"]
    ),
    
    # ==========================================================================
    # PSYCHOLOGY - Real books: book_thinking_fast_slow, book_thinking
    # ==========================================================================
    TaxonomyMapping(
        domain="Psychology",
        subdomain="Cognitive Science",
        book_ids=["book_thinking_fast_slow", "book_thinking", "mock_thinking_fast"]
    ),
    TaxonomyMapping(
        domain="Psychology",
        subdomain="Cognitive Psychology",
        book_ids=["book_thinking_fast_slow", "mock_thinking_fast"]
    ),
    TaxonomyMapping(
        domain="Psychology",
        subdomain="Social Psychology",
        book_ids=["mock_influence"]
    ),
    TaxonomyMapping(
        domain="Psychology",
        subdomain="Organizational Psychology",
        book_ids=["book_thinking_fast_slow", "mock_influence", "mock_righteous_mind"]
    ),
    TaxonomyMapping(
        domain="Psychology",
        subdomain=None,
        book_ids=["book_thinking_fast_slow", "book_thinking", "mock_thinking_fast", "mock_influence", "mock_righteous_mind"]
    ),
    
    # ==========================================================================
    # ECONOMICS - Real books: book_wealth_nations, book_wealth
    # ==========================================================================
    TaxonomyMapping(
        domain="Economics",
        subdomain="Political Economy",
        book_ids=["book_wealth_nations", "mock_wealth_nations", "mock_capital"]
    ),
    TaxonomyMapping(
        domain="Economics",
        subdomain="Microeconomics",
        book_ids=["book_wealth", "book_wealth_nations"]
    ),
    TaxonomyMapping(
        domain="Economics",
        subdomain=None,
        book_ids=["book_wealth_nations", "book_wealth", "mock_wealth_nations", "mock_capital"]
    ),
    
    # ==========================================================================
    # BUSINESS - Maps to Strategy books for now
    # ==========================================================================
    TaxonomyMapping(
        domain="Business",
        subdomain="Entrepreneurship",
        book_ids=["mock_zero_to_one"]
    ),
    TaxonomyMapping(
        domain="Business",
        subdomain="Management",
        book_ids=["mock_good_to_great"]
    ),
    TaxonomyMapping(
        domain="Business",
        subdomain="Leadership",
        book_ids=["book_prince", "mock_good_to_great"]
    ),
    TaxonomyMapping(
        domain="Business",
        subdomain=None,
        book_ids=["book_prince", "mock_zero_to_one", "mock_good_to_great"]
    ),
    
    # ==========================================================================
    # TECHNOLOGY - Real books: book_cleancode, book_mythical_man_month
    # ==========================================================================
    TaxonomyMapping(
        domain="Technology",
        subdomain="Software Engineering",
        book_ids=["book_cleancode", "book_mythical_man_month", "mock_mythical_man"]
    ),
    TaxonomyMapping(
        domain="Technology",
        subdomain="Systems Design",
        book_ids=["book_mythical_man_month", "mock_thinking_systems"]
    ),
    TaxonomyMapping(
        domain="Technology",
        subdomain=None,
        book_ids=["book_cleancode", "book_mythical_man_month", "mock_mythical_man", "mock_thinking_systems"]
    ),
    
    # ==========================================================================
    # HISTORY - Mock only for now
    # ==========================================================================
    TaxonomyMapping(
        domain="History",
        subdomain="Ancient History",
        book_ids=["book_republic", "mock_decline_fall"]
    ),
    TaxonomyMapping(
        domain="History",
        subdomain=None,
        book_ids=["book_republic", "mock_decline_fall", "mock_guns_germs"]
    ),
    
    # ==========================================================================
    # POLITICS - Real book: book_republic
    # ==========================================================================
    TaxonomyMapping(
        domain="Politics",
        subdomain="Political Theory",
        book_ids=["book_republic", "book_prince", "mock_leviathan", "mock_two_treatises"]
    ),
    TaxonomyMapping(
        domain="Politics",
        subdomain=None,
        book_ids=["book_republic", "book_prince", "mock_leviathan", "mock_two_treatises"]
    ),
    
    # ==========================================================================
    # RELIGION - Mock only for now
    # ==========================================================================
    TaxonomyMapping(
        domain="Religion",
        subdomain="Spirituality",
        book_ids=["book_meditations", "mock_varieties"]
    ),
    TaxonomyMapping(
        domain="Religion",
        subdomain="Eastern Philosophy",
        book_ids=["mock_tao_te_ching"]
    ),
    TaxonomyMapping(
        domain="Religion",
        subdomain=None,
        book_ids=["book_meditations", "mock_varieties", "mock_tao_te_ching"]
    ),
    
    # ==========================================================================
    # SOCIOLOGY - Mock only for now
    # ==========================================================================
    TaxonomyMapping(
        domain="Sociology",
        subdomain="Social Theory",
        book_ids=["mock_protestant_ethic"]
    ),
    TaxonomyMapping(
        domain="Sociology",
        subdomain="Institutions",
        book_ids=["book_wealth_nations", "mock_protestant_ethic"]
    ),
    TaxonomyMapping(
        domain="Sociology",
        subdomain=None,
        book_ids=["book_wealth_nations", "mock_protestant_ethic"]
    ),
    
    # ==========================================================================
    # SCIENCE - Mock only for now
    # ==========================================================================
    TaxonomyMapping(
        domain="Science",
        subdomain="Evolution",
        book_ids=["mock_origin_species"]
    ),
    TaxonomyMapping(
        domain="Science",
        subdomain="Scientific Method",
        book_ids=["mock_structure_revolutions"]
    ),
    TaxonomyMapping(
        domain="Science",
        subdomain=None,
        book_ids=["mock_origin_species", "mock_structure_revolutions"]
    ),
    
    # ==========================================================================
    # LITERATURE - Mock only for now
    # ==========================================================================
    TaxonomyMapping(
        domain="Literature",
        subdomain="Literary Criticism",
        book_ids=["mock_poetics"]
    ),
    TaxonomyMapping(
        domain="Literature",
        subdomain="Mythology",
        book_ids=["mock_hero_thousand"]
    ),
    TaxonomyMapping(
        domain="Literature",
        subdomain=None,
        book_ids=["mock_poetics", "mock_hero_thousand"]
    ),
    
    # ==========================================================================
    # LAW - Mock only for now
    # ==========================================================================
    TaxonomyMapping(
        domain="Law",
        subdomain="Legal Theory",
        book_ids=["mock_spirit_laws"]
    ),
    TaxonomyMapping(
        domain="Law",
        subdomain=None,
        book_ids=["mock_spirit_laws"]
    ),
    
    # ==========================================================================
    # ART - Mock only for now
    # ==========================================================================
    TaxonomyMapping(
        domain="Art",
        subdomain="Aesthetics",
        book_ids=["mock_art_spirit"]
    ),
    TaxonomyMapping(
        domain="Art",
        subdomain=None,
        book_ids=["mock_art_spirit"]
    ),
    
    # ==========================================================================
    # MATHEMATICS - Mock only for now
    # ==========================================================================
    TaxonomyMapping(
        domain="Mathematics",
        subdomain="Geometry",
        book_ids=["mock_elements"]
    ),
    TaxonomyMapping(
        domain="Mathematics",
        subdomain=None,
        book_ids=["mock_elements"]
    ),
    
    # ==========================================================================
    # MEDICINE - Mock only for now
    # ==========================================================================
    TaxonomyMapping(
        domain="Medicine",
        subdomain=None,
        book_ids=["mock_how_we_die"]
    ),
    
    # ==========================================================================
    # COMMUNICATION - Mock only for now
    # ==========================================================================
    TaxonomyMapping(
        domain="Communication",
        subdomain="Rhetoric",
        book_ids=["mock_rhetoric"]
    ),
    TaxonomyMapping(
        domain="Communication",
        subdomain=None,
        book_ids=["mock_rhetoric"]
    ),
]


# Build lookup index for fast access
_TAXONOMY_INDEX: dict = {}


def _build_index():
    """Build domain+subdomain lookup index."""
    global _TAXONOMY_INDEX
    _TAXONOMY_INDEX.clear()
    
    for mapping in TAXONOMY:
        key = f"{mapping.domain}::{mapping.subdomain or '*'}"
        if key not in _TAXONOMY_INDEX:
            _TAXONOMY_INDEX[key] = []
        _TAXONOMY_INDEX[key].extend(mapping.book_ids)


# Build index on module load
_build_index()


# =============================================================================
# PUBLIC API
# =============================================================================

def get_candidate_books(
    domain: str,
    subdomain: Optional[str] = None,
    max_books: int = 12
) -> List[str]:
    """
    Get candidate book IDs for a domain/subdomain.
    
    Lookup strategy:
    1. Try exact match: domain + subdomain
    2. Fallback to domain + wildcard (subdomain=None)
    3. Return empty list if no match
    
    Args:
        domain: Primary domain
        subdomain: Optional subdomain
        max_books: Cap on number of books returned
        
    Returns:
        List of book_ids (max 12)
    """
    candidates: Set[str] = set()
    
    # Try exact match first
    if subdomain:
        exact_key = f"{domain}::{subdomain}"
        if exact_key in _TAXONOMY_INDEX:
            candidates.update(_TAXONOMY_INDEX[exact_key])
    
    # Fallback to domain wildcard
    wildcard_key = f"{domain}::*"
    if wildcard_key in _TAXONOMY_INDEX:
        candidates.update(_TAXONOMY_INDEX[wildcard_key])
    
    # Cap at max_books
    return list(candidates)[:max_books]


def get_taxonomy_version() -> int:
    """Get current taxonomy version (for cache keys)."""
    return TAXONOMY_VERSION


def validate_book_id(book_id: str) -> bool:
    """Check if a book_id exists in ANY taxonomy mapping."""
    return any(book_id in mapping.book_ids for mapping in TAXONOMY)


def get_all_taxonomy_book_ids() -> Set[str]:
    """Get all book IDs referenced in taxonomy."""
    all_ids: Set[str] = set()
    for mapping in TAXONOMY:
        all_ids.update(mapping.book_ids)
    return all_ids


# =============================================================================
# ADMIN/MAINTENANCE HELPERS
# =============================================================================

def get_taxonomy_coverage() -> dict:
    """Get statistics about taxonomy coverage."""
    return {
        "total_mappings": len(TAXONOMY),
        "unique_books": len(get_all_taxonomy_book_ids()),
        "domains": len(set(m.domain for m in TAXONOMY)),
        "version": TAXONOMY_VERSION,
        "mappings_by_domain": {
            domain: len([m for m in TAXONOMY if m.domain == domain])
            for domain in set(m.domain for m in TAXONOMY)
        }
    }


def rebuild_taxonomy_from_db(books: List[dict]):
    """
    Helper to rebuild taxonomy from database books.
    NOT IMPLEMENTED YET - for future use.
    
    Would query books table, group by domain/subdomain,
    and regenerate TAXONOMY list.
    """
    raise NotImplementedError("Dynamic taxonomy rebuild not yet implemented")

