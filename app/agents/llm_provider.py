"""
Alexandria Library - LLM Provider
Centralized OpenAI client with retries, timeouts, and usage logging.

This is the ONLY place where OpenAI API calls should be made.
All agents use this provider.
"""

import json
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime

from openai import OpenAI, APIError, APITimeoutError, RateLimitError
from ..config import settings


@dataclass
class LLMUsage:
    """Track token usage for monitoring/budgeting."""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    model: str
    timestamp: datetime
    agent: str  # Which agent made the call
    

class LLMProvider:
    """
    Centralized OpenAI client wrapper.
    
    Features:
    - Bounded retries with exponential backoff
    - Timeout enforcement
    - Usage logging
    - Structured output parsing
    - Graceful degradation
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = None,
        max_retries: int = 3,
        timeout: int = 30
    ):
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.model = model or settings.OPENAI_MODEL
        self.max_retries = max_retries
        self.timeout = timeout
        self.usage_log: List[LLMUsage] = []
        
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not set")
        
        self.client = OpenAI(
            api_key=self.api_key,
            timeout=self.timeout
        )
    
    def call(
        self,
        system_prompt: str,
        user_prompt: str,
        agent_name: str,
        temperature: float = 0.3,
        max_tokens: int = 500,
        response_format: str = "json"  # "json" or "text"
    ) -> Dict[str, Any]:
        """
        Make an LLM call with retries and error handling.
        
        Args:
            system_prompt: System instructions
            user_prompt: User input
            agent_name: Which agent is calling (for logging)
            temperature: Sampling temperature
            max_tokens: Max completion tokens
            response_format: "json" or "text"
            
        Returns:
            Parsed JSON dict (if response_format="json") or {"text": str}
            
        Raises:
            Exception: After max_retries exhausted
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        last_error = None
        for attempt in range(self.max_retries):
            try:
                start_time = time.time()
                
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                
                elapsed = time.time() - start_time
                
                # Log usage
                if response.usage:
                    usage = LLMUsage(
                        prompt_tokens=response.usage.prompt_tokens,
                        completion_tokens=response.usage.completion_tokens,
                        total_tokens=response.usage.total_tokens,
                        model=self.model,
                        timestamp=datetime.now(),
                        agent=agent_name
                    )
                    self.usage_log.append(usage)
                
                # Extract and parse response
                content = response.choices[0].message.content
                
                if response_format == "json":
                    try:
                        parsed = json.loads(content)
                        return parsed
                    except json.JSONDecodeError as e:
                        # Try to extract JSON from text
                        content_clean = content.strip()
                        if content_clean.startswith("```json"):
                            content_clean = content_clean[7:]
                        if content_clean.startswith("```"):
                            content_clean = content_clean[3:]
                        if content_clean.endswith("```"):
                            content_clean = content_clean[:-3]
                        parsed = json.loads(content_clean.strip())
                        return parsed
                else:
                    return {"text": content}
                    
            except (APITimeoutError, RateLimitError) as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    # Exponential backoff: 1s, 2s, 4s
                    wait_time = 2 ** attempt
                    time.sleep(wait_time)
                    continue
                raise
                
            except APIError as e:
                # Don't retry on API errors (likely bad request)
                raise
                
            except json.JSONDecodeError as e:
                # Failed to parse JSON after cleanup attempt
                raise ValueError(f"LLM returned invalid JSON: {content[:200]}")
        
        # Max retries exhausted
        raise Exception(f"LLM call failed after {self.max_retries} attempts: {last_error}")
    
    def get_usage_summary(self) -> Dict[str, Any]:
        """Get summary of token usage."""
        if not self.usage_log:
            return {
                "total_calls": 0,
                "total_tokens": 0,
                "by_agent": {}
            }
        
        total_tokens = sum(u.total_tokens for u in self.usage_log)
        by_agent = {}
        
        for usage in self.usage_log:
            if usage.agent not in by_agent:
                by_agent[usage.agent] = {
                    "calls": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0
                }
            by_agent[usage.agent]["calls"] += 1
            by_agent[usage.agent]["prompt_tokens"] += usage.prompt_tokens
            by_agent[usage.agent]["completion_tokens"] += usage.completion_tokens
            by_agent[usage.agent]["total_tokens"] += usage.total_tokens
        
        return {
            "total_calls": len(self.usage_log),
            "total_tokens": total_tokens,
            "by_agent": by_agent
        }
    
    def clear_usage_log(self):
        """Clear usage log (useful for testing)."""
        self.usage_log.clear()


# Singleton instance (lazy-initialized)
_provider: Optional[LLMProvider] = None


def get_llm_provider() -> LLMProvider:
    """Get or create the global LLM provider instance."""
    global _provider
    if _provider is None:
        _provider = LLMProvider()
    return _provider


def reset_llm_provider():
    """Reset provider (useful for testing)."""
    global _provider
    _provider = None

