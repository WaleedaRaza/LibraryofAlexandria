"""
Alexandria Library - Routing Cache
Caches routing results to avoid redundant LLM calls.

Cache key: normalized(query) + taxonomy_version
TTL: 1 hour (configurable)

This is an in-memory cache for V1. In production, use Redis or similar.
"""

import hashlib
import time
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict

from .contracts import RoutingResult

# Try to get version from V2 taxonomy, fallback to V1
try:
    from .taxonomy_v2 import get_taxonomy_gate
    def get_taxonomy_version() -> int:
        try:
            gate = get_taxonomy_gate()
            # Use artifact version for cache key (more specific than taxonomy version)
            return gate.get_artifact_version()
        except:
            return 1
except:
    from .taxonomy import get_taxonomy_version


@dataclass
class CacheEntry:
    """A cached routing result."""
    routing_result: RoutingResult
    cached_at: float  # Unix timestamp
    taxonomy_version: int
    query_hash: str


class RoutingCache:
    """
    In-memory cache for routing results.
    
    Cache invalidation:
    - TTL expires (default 1 hour)
    - Taxonomy version changes
    - Manual clear
    """
    
    def __init__(self, ttl_seconds: int = 3600):
        self.cache: Dict[str, CacheEntry] = {}
        self.ttl_seconds = ttl_seconds
        self.hits = 0
        self.misses = 0
    
    def _normalize_query(self, query: str) -> str:
        """
        Normalize query for cache lookup.
        - Lowercase
        - Strip whitespace
        - Remove punctuation
        """
        normalized = query.lower().strip()
        # Remove common punctuation
        for char in "?!.,;:":
            normalized = normalized.replace(char, "")
        # Collapse multiple spaces
        normalized = " ".join(normalized.split())
        return normalized
    
    def _compute_cache_key(self, query: str, domain: str, subdomain: Optional[str]) -> str:
        """
        Compute cache key from query + domain/subdomain + taxonomy version.
        
        Key format: sha256(normalized_query + domain + subdomain + tax_version)
        """
        normalized = self._normalize_query(query)
        taxonomy_ver = get_taxonomy_version()
        
        key_components = f"{normalized}::{domain}::{subdomain or ''}::{taxonomy_ver}"
        key_hash = hashlib.sha256(key_components.encode()).hexdigest()[:16]
        
        return key_hash
    
    def get(
        self,
        query: str,
        domain: str,
        subdomain: Optional[str] = None
    ) -> Optional[RoutingResult]:
        """
        Get cached routing result if available and valid.
        
        Returns:
            RoutingResult if cache hit, None if miss
        """
        cache_key = self._compute_cache_key(query, domain, subdomain)
        
        if cache_key not in self.cache:
            self.misses += 1
            return None
        
        entry = self.cache[cache_key]
        
        # Check if expired
        age = time.time() - entry.cached_at
        if age > self.ttl_seconds:
            # Expired, remove from cache
            del self.cache[cache_key]
            self.misses += 1
            return None
        
        # Check if taxonomy version changed
        if entry.taxonomy_version != get_taxonomy_version():
            # Taxonomy changed, invalidate
            del self.cache[cache_key]
            self.misses += 1
            return None
        
        # Valid cache hit
        self.hits += 1
        return entry.routing_result
    
    def set(
        self,
        query: str,
        domain: str,
        subdomain: Optional[str],
        routing_result: RoutingResult
    ):
        """
        Cache a routing result.
        
        Args:
            query: Original query
            domain: Classified domain
            subdomain: Classified subdomain
            routing_result: Result to cache
        """
        cache_key = self._compute_cache_key(query, domain, subdomain)
        
        entry = CacheEntry(
            routing_result=routing_result,
            cached_at=time.time(),
            taxonomy_version=get_taxonomy_version(),
            query_hash=cache_key
        )
        
        self.cache[cache_key] = entry
    
    def clear(self):
        """Clear all cached entries."""
        self.cache.clear()
        self.hits = 0
        self.misses = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_requests = self.hits + self.misses
        hit_rate = (self.hits / total_requests * 100) if total_requests > 0 else 0
        
        return {
            "total_entries": len(self.cache),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate_percent": round(hit_rate, 2),
            "ttl_seconds": self.ttl_seconds,
            "taxonomy_version": get_taxonomy_version()
        }
    
    def prune_expired(self):
        """Remove expired entries from cache."""
        now = time.time()
        expired_keys = [
            key for key, entry in self.cache.items()
            if (now - entry.cached_at) > self.ttl_seconds
        ]
        for key in expired_keys:
            del self.cache[key]
        return len(expired_keys)


# Global cache instance
_cache: Optional[RoutingCache] = None


def get_routing_cache() -> RoutingCache:
    """Get or create the global routing cache."""
    global _cache
    if _cache is None:
        _cache = RoutingCache()
    return _cache


def reset_routing_cache():
    """Reset cache (useful for testing)."""
    global _cache
    if _cache:
        _cache.clear()
    _cache = None

