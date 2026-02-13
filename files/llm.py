"""Thin Ollama client. All LLM calls go through here."""

from __future__ import annotations
import json
import time
import httpx
from rich.console import Console

console = Console()


class LLMError(Exception):
    """LLM call failed after retries."""
    pass


class OllamaClient:
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.1:8b",
        temperature: float = 0.3,
        timeout: int = 600,
        max_retries: int = 2,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.timeout = timeout
        self.max_retries = max_retries
        self._client = httpx.Client(timeout=timeout)
        self._call_count = 0
        self._total_time = 0.0

    def generate_json(self, prompt: str, system: str | None = None) -> dict:
        """Send prompt, expect JSON response, parse and return.

        Uses Ollama's format: "json" to force structured output.
        Retries on parse failure or connection error.
        Logs timing for every call.
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        prompt_chars = len(prompt) + (len(system) if system else 0)

        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                t0 = time.time()
                response = self._client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": messages,
                        "stream": False,
                        "options": {"temperature": self.temperature},
                        "format": "json",
                    },
                )
                elapsed = time.time() - t0
                self._call_count += 1
                self._total_time += elapsed

                response.raise_for_status()
                content = response.json()["message"]["content"]
                result = json.loads(content)

                console.print(
                    f"    [dim]LLM call #{self._call_count}: "
                    f"{prompt_chars:,} chars in → {len(content):,} chars out, "
                    f"{elapsed:.1f}s[/dim]"
                )

                return result

            except json.JSONDecodeError as e:
                elapsed = time.time() - t0
                last_error = e
                console.print(
                    f"    [yellow]JSON parse failed (attempt {attempt + 1}/{self.max_retries + 1}, "
                    f"{elapsed:.1f}s), retrying...[/yellow]"
                )
                time.sleep(1)

            except httpx.ReadTimeout as e:
                elapsed = time.time() - t0
                last_error = e
                console.print(
                    f"    [red]TIMEOUT after {elapsed:.1f}s "
                    f"(attempt {attempt + 1}/{self.max_retries + 1}, "
                    f"prompt: {prompt_chars:,} chars)[/red]"
                )
                time.sleep(2)

            except (httpx.HTTPError, httpx.ConnectError, KeyError) as e:
                elapsed = time.time() - t0 if 't0' in dir() else 0
                last_error = e
                console.print(
                    f"    [yellow]LLM request failed (attempt {attempt + 1}): {e}[/yellow]"
                )
                time.sleep(2 * (attempt + 1))

        raise LLMError(
            f"LLM call failed after {self.max_retries + 1} attempts: {last_error}"
        )

    def generate_text(self, prompt: str, system: str | None = None) -> str:
        """For non-structured responses."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        t0 = time.time()
        response = self._client.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": self.temperature},
            },
        )
        elapsed = time.time() - t0
        response.raise_for_status()

        content = response.json()["message"]["content"]
        console.print(f"    [dim]LLM text call: {elapsed:.1f}s[/dim]")
        return content

    def is_available(self) -> bool:
        """Check if Ollama is running and model is loaded."""
        try:
            r = self._client.get(f"{self.base_url}/api/tags")
            r.raise_for_status()
            models = [m["name"] for m in r.json().get("models", [])]
            model_base = self.model.split(":")[0]
            return any(model_base in m for m in models)
        except Exception:
            return False

    def stats(self) -> str:
        """Return call stats summary."""
        if self._call_count == 0:
            return "No LLM calls made"
        avg = self._total_time / self._call_count
        return (
            f"{self._call_count} calls, "
            f"{self._total_time:.1f}s total, "
            f"{avg:.1f}s avg"
        )
