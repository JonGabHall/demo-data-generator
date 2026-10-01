"""Optional fact-constrained narrative generation through a localhost LLM."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any, Callable
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class NarrativeStats:
    total_calls: int
    requests_sent: int
    accepted_responses: int
    fallback_responses: int
    budget_fallbacks: int
    invalid_response_fallbacks: int
    request_error_fallbacks: int


class LocalJsonNarrator:
    """Generate short text while treating deterministic fallback text as authoritative."""

    def __init__(
        self,
        endpoint: str,
        model: str,
        timeout_seconds: float = 20,
        max_requests: int = 100,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        if not endpoint.lower().startswith(("http://localhost", "http://127.0.0.1")):
            raise ValueError("The narrative endpoint must use localhost or 127.0.0.1.")
        if not model.strip():
            raise ValueError("The narrative model cannot be empty.")
        if max_requests < 0:
            raise ValueError("max_requests cannot be negative.")
        self.endpoint = endpoint
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_requests = max_requests
        self._opener = opener
        self._request_count = 0
        self._total_calls = 0
        self._accepted_responses = 0
        self._budget_fallbacks = 0
        self._invalid_response_fallbacks = 0
        self._request_error_fallbacks = 0

    @property
    def stats(self) -> NarrativeStats:
        fallback_responses = (
            self._budget_fallbacks
            + self._invalid_response_fallbacks
            + self._request_error_fallbacks
        )
        return NarrativeStats(
            total_calls=self._total_calls,
            requests_sent=self._request_count,
            accepted_responses=self._accepted_responses,
            fallback_responses=fallback_responses,
            budget_fallbacks=self._budget_fallbacks,
            invalid_response_fallbacks=self._invalid_response_fallbacks,
            request_error_fallbacks=self._request_error_fallbacks,
        )

    def narrate(self, record_type: str, facts: dict[str, object], fallback: str) -> str:
        self._total_calls += 1
        if self._request_count >= self.max_requests:
            self._budget_fallbacks += 1
            return fallback
        self._request_count += 1
        try:
            request = Request(
                self.endpoint,
                data=json.dumps(self._request_body(record_type, facts)).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with self._opener(request, timeout=self.timeout_seconds) as response:
                outer = json.loads(response.read().decode("utf-8"))
            content = self._response_content(outer)
            payload = json.loads(content)
            if set(payload) != {"text"} or not isinstance(payload["text"], str):
                self._invalid_response_fallbacks += 1
                return fallback
            text = " ".join(payload["text"].split())
            if not text or len(text) > 500:
                self._invalid_response_fallbacks += 1
                return fallback
            self._accepted_responses += 1
            return text
        except (OSError, TimeoutError):
            self._request_error_fallbacks += 1
            return fallback
        except (ValueError, TypeError, KeyError, IndexError, json.JSONDecodeError):
            self._invalid_response_fallbacks += 1
            return fallback

    def _request_body(self, record_type: str, facts: dict[str, object]) -> dict[str, object]:
        prompt = (
            "Write one concise synthetic asset-management narrative using only the supplied facts. "
            "Do not invent people, identifiers, dates, measurements, actions, or findings. "
            "Return JSON only with exactly one key named text and no Markdown. "
            f"Record type: {record_type}. Facts: {json.dumps(facts, sort_keys=True)}"
        )
        if self.endpoint.rstrip("/").endswith("/api/generate"):
            return {
                "model": self.model,
                "prompt": prompt,
                "format": "json",
                "stream": False,
            }
        return {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        }

    def _response_content(self, payload: dict[str, object]) -> str:
        if self.endpoint.rstrip("/").endswith("/api/generate"):
            content = payload["response"]
        else:
            choices = payload["choices"]
            if not isinstance(choices, list):
                raise TypeError("choices must be a list")
            choice = choices[0]
            if not isinstance(choice, dict):
                raise TypeError("choice must be an object")
            message = choice["message"]
            if not isinstance(message, dict):
                raise TypeError("message must be an object")
            content = message["content"]
        if not isinstance(content, str):
            raise TypeError("narrative content must be text")
        return content


def narrative_run_metadata(
    narrator: LocalJsonNarrator | None,
) -> dict[str, object]:
    """Describe whether and how local narrative generation was used."""
    if narrator is None:
        statistics = NarrativeStats(0, 0, 0, 0, 0, 0, 0)
        return {
            "enabled": False,
            "endpoint": None,
            "model": None,
            "maximum_requests": 0,
            "fallback": "deterministic",
            "statistics": asdict(statistics),
        }
    return {
        "enabled": True,
        "endpoint": narrator.endpoint,
        "model": narrator.model,
        "maximum_requests": narrator.max_requests,
        "fallback": "deterministic",
        "statistics": asdict(narrator.stats),
    }