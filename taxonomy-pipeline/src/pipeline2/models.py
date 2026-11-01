"""Model endpoints behind config. Nothing here is required for S0-S6 or BM25 routing.

Ollama (default, local):          base_url http://localhost:11434
OpenAI-compatible (LM Studio,
llama.cpp server, vLLM):          provider openai, base_url http://localhost:1234/v1
Reranker (cross-encoder):         provider http, url http://127.0.0.1:8088/rerank
                                  (llama.cpp --reranking, TEI, or Jina-style /rerank)
"""
from __future__ import annotations
import json
import math
import time
from dataclasses import dataclass

import httpx


@dataclass
class EmbedConfig:
    provider: str = "none"          # none | ollama | openai
    base_url: str = "http://localhost:11434"
    model: str = "qwen3-embedding:4b"
    batch: int = 32
    query_prefix: str = ""          # e.g. "search_query: " for nomic, "query: " for e5
    doc_prefix: str = ""            # e.g. "search_document: "
    timeout: int = 300


@dataclass
class GenConfig:
    provider: str = "none"          # none | ollama | openai
    base_url: str = "http://localhost:11434"
    model: str = "gemma4:12b"
    temperature: float = 0.0
    timeout: int = 600
    think: bool | None = None       # ollama only; false for thinking models (gemma4, qwen3) so content is the JSON
    num_ctx: int | None = None      # ollama only


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
                    opts = {"temperature": self.cfg.temperature}
                    if self.cfg.num_ctx:
                        opts["num_ctx"] = self.cfg.num_ctx
                    body = {"model": self.cfg.model, "stream": False, "format": schema, "options": opts,
                            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
                    if self.cfg.think is not None:
                        body["think"] = self.cfg.think
                    r = self.http.post(f"{self.cfg.base_url.rstrip('/')}/api/chat", json=body)
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


@dataclass
class RerankConfig:
    provider: str = "none"          # none | http
    url: str = "http://127.0.0.1:8088/rerank"
    model: str = "bge-reranker-v2-m3"
    top: int = 30                   # how many fused candidates to rerank
    max_chars: int = 2000           # passage text sent per candidate
    timeout: int = 120


class Reranker:
    """Cross-encoder rerank over an HTTP /rerank endpoint.

    Sends {"query", "documents", "texts", "model"} so llama.cpp, Jina-style and TEI servers all accept it,
    and reads either {"results": [{"index", "relevance_score"}]} or [{"index", "score"}]."""

    def __init__(self, cfg: RerankConfig):
        self.cfg = cfg
        self.http = httpx.Client(timeout=cfg.timeout)

    @property
    def enabled(self) -> bool:
        return self.cfg.provider != "none"

    def scores(self, query: str, docs: list[str]) -> list[float]:
        docs = [d[: self.cfg.max_chars] for d in docs]
        r = self.http.post(self.cfg.url, json={"model": self.cfg.model, "query": query,
                                               "documents": docs, "texts": docs})
        r.raise_for_status()
        data = r.json()
        rows = data.get("results", data.get("data", [])) if isinstance(data, dict) else data
        out = [float("-inf")] * len(docs)
        for row in rows:
            out[int(row["index"])] = float(row.get("relevance_score", row.get("score")))
        # logits -> probabilities so zone weights multiply sensibly; leave scores already in [0,1]
        if any(s < 0 or s > 1 for s in out if s != float("-inf")):
            out = [1 / (1 + math.exp(-s)) if s != float("-inf") else 0.0 for s in out]
        return out
