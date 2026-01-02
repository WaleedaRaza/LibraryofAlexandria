"""
Alexandria Library - Rate Limit Middleware

Simple in-memory rate limiting for V1.
Future: Replace with Redis for distributed deployments.

DESIGN:
- Per-IP rate limiting by default
- Per-user rate limiting when authenticated
- Different limits for different endpoint types
- Graceful degradation (fail open with warning, not closed)

USAGE:
    @rate_limit(requests=10, window=60)  # 10 requests per 60 seconds
    async def my_endpoint(...):
        ...
"""

import time
from collections import defaultdict
from functools import wraps
from typing import Callable, Optional
from fastapi import Request, HTTPException


class RateLimiter:
    """
    Simple in-memory rate limiter.
    
    Uses sliding window algorithm.
    NOT suitable for distributed deployment (use Redis instead).
    """
    
    def __init__(self):
        # Structure: {key: [(timestamp, count), ...]}
        self._requests: dict = defaultdict(list)
        
        # Default limits (can be overridden per-endpoint)
        self.default_limits = {
            "ask": (10, 60),      # 10 asks per minute
            "chat": (30, 60),     # 30 chat messages per minute
            "highlight": (60, 60), # 60 highlights per minute
            "default": (100, 60),  # 100 requests per minute
        }
    
    def _clean_old_requests(self, key: str, window: int):
        """Remove requests outside the window."""
        cutoff = time.time() - window
        self._requests[key] = [
            (ts, count) for ts, count in self._requests[key]
            if ts > cutoff
        ]
    
    def _count_requests(self, key: str) -> int:
        """Count requests in current window."""
        return sum(count for _, count in self._requests[key])
    
    def is_allowed(
        self, 
        key: str, 
        requests: int, 
        window: int
    ) -> tuple[bool, int]:
        """
        Check if request is allowed.
        
        Returns:
            (is_allowed, remaining_requests)
        """
        self._clean_old_requests(key, window)
        current_count = self._count_requests(key)
        
        if current_count >= requests:
            return False, 0
        
        # Record this request
        self._requests[key].append((time.time(), 1))
        
        return True, requests - current_count - 1
    
    def get_key(self, request: Request, user: Optional[dict] = None) -> str:
        """
        Get rate limit key for a request.
        
        Uses user_id if authenticated, else IP address.
        """
        if user and user.get("id"):
            return f"user:{user['id']}"
        
        # Use X-Forwarded-For if behind proxy, else client host
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
        else:
            ip = request.client.host if request.client else "unknown"
        
        return f"ip:{ip}"


# Global rate limiter instance
_limiter = RateLimiter()


def rate_limit(
    requests: int = 100,
    window: int = 60,
    endpoint_type: str = "default"
):
    """
    Rate limit decorator for FastAPI endpoints.
    
    Args:
        requests: Max requests allowed
        window: Time window in seconds
        endpoint_type: Type of endpoint (for logging/metrics)
    
    Usage:
        @router.post("/ask")
        @rate_limit(requests=10, window=60, endpoint_type="ask")
        async def ask_endpoint(...):
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract request from kwargs
            request: Request = kwargs.get("request")
            user = kwargs.get("user")
            
            if request is None:
                # Can't rate limit without request, proceed anyway
                return await func(*args, **kwargs)
            
            key = f"{_limiter.get_key(request, user)}:{endpoint_type}"
            is_allowed, remaining = _limiter.is_allowed(key, requests, window)
            
            if not is_allowed:
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded. Try again in {window} seconds.",
                    headers={"Retry-After": str(window)}
                )
            
            # Add rate limit headers to response
            # (Would need response middleware for this, skipping for V1)
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


def get_limiter() -> RateLimiter:
    """Get the global rate limiter instance."""
    return _limiter

