"""Model endpoints behind config. Nothing here is required for S0-S6 or BM25 routing.

Ollama (default, local):          base_url http://localhost:11434
OpenAI-compatible (LM Studio,
llama.cpp server, vLLM):          provider openai, base_url http://localhost:1234/v1
"""
from __future__ import annotations
import json
import time
from dataclasses import dataclass

import httpx


@dataclass
class EmbedConfig:
    provider: str = "none"          # none | ollama | openai
    base_url: str = "http://localhost:11434"
    model: str = "nomic-embed-text"
    batch: int = 32
    query_prefix: str = ""          # e.g. "search_query: " for nomic, "query: " for e5
    doc_prefix: str = ""            # e.g. "search_document: "
    timeout: int = 300


@dataclass
class GenConfig:
    provider: str = "none"          # none | ollama | openai
    base_url: str = "http://localhost:11434"
    model: str = "qwen2.5:7b-instruct"
    temperature: float = 0.0
    timeout: int = 600


class Embedder:
    def __init__(self, cfg: EmbedConfig):
        self.cfg = cfg
        self.http = httpx.Client(timeout=cfg.timeout)

    @property
    def enabled(self) -> bool:
        return self.cfg.provider != "none"

    def embed(self, texts: list[str], query: bool = False) -> list[list[float]]:
        pre = self.cfg.query_prefix if query else self.cfg.doc_prefix
        out: list[list[float]] = []
        for i in range(0, len(texts), self.cfg.batch):
            chunk = [pre + t for t in texts[i:i + self.cfg.batch]]
            if self.cfg.provider == "ollama":
                r = self.http.post(f"{self.cfg.base_url.rstrip('/')}/api/embed", json={"model": self.cfg.model, "input": chunk})
                r.raise_for_status()
                out.extend(r.json()["embeddings"])
            elif self.cfg.provider == "openai":
                r = self.http.post(f"{self.cfg.base_url.rstrip('/')}/embeddings", json={"model": self.cfg.model, "input": chunk})
                r.raise_for_status()
                out.extend(d["embedding"] for d in sorted(r.json()["data"], key=lambda d: d["index"]))
            else:
                raise RuntimeError("embedding provider is 'none'")
        return out


class Generator:
    """JSON-only generation with a schema, temperature 0 by default."""

    def __init__(self, cfg: GenConfig):
        self.cfg = cfg
        self.http = httpx.Client(timeout=cfg.timeout)

    @property
    def enabled(self) -> bool:
        return self.cfg.provider != "none"

    def json(self, system: str, user: str, schema: dict, retries: int = 2) -> dict:
        last = None
        for _ in range(retries + 1):
            try:
                if self.cfg.provider == "ollama":
                    r = self.http.post(f"{self.cfg.base_url.rstrip('/')}/api/chat", json={
                        "model": self.cfg.model, "stream": False, "format": schema,
                        "options": {"temperature": self.cfg.temperature},
                        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
                    r.raise_for_status()
                    return json.loads(r.json()["message"]["content"])
                if self.cfg.provider == "openai":
                    r = self.http.post(f"{self.cfg.base_url.rstrip('/')}/chat/completions", json={
                        "model": self.cfg.model, "temperature": self.cfg.temperature,
                        "response_format": {"type": "json_schema", "json_schema": {"name": "out", "schema": schema}},
                        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
                    r.raise_for_status()
                    return json.loads(r.json()["choices"][0]["message"]["content"])
                raise RuntimeError("generation provider is 'none'")
            except (httpx.HTTPError, json.JSONDecodeError, KeyError) as e:
                last = e
                time.sleep(1)
        raise RuntimeError(f"generation failed: {last}")
