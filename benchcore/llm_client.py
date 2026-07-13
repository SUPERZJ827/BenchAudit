from __future__ import annotations

import hashlib
import http.client
import json
import os
import ssl
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


@dataclass
class LLMConfig:
    model: str
    base_url: str
    api_key_env: str = "FIN_API"
    temperature: float = 0.0
    timeout: int = 120
    max_tokens: int = 1200
    max_retries: int = 3
    cache_path: str | None = None
    dry_run: bool = False
    n_votes: int = 1          # 1 = no voting; 3 = majority-vote (3 calls with vote_temperature)
    vote_temperature: float = 0.3  # temperature used for voting calls (must be > 0 for variance)


def load_llm_config(path: str | None = None) -> LLMConfig:
    data: dict[str, Any] = {}
    if path:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    return LLMConfig(
        model=data.get("model", "deepseek-v4-flash"),
        base_url=data.get("base_url", "https://api.deepseek.com"),
        api_key_env=data.get("api_key_env", "FIN_API"),
        temperature=float(data.get("temperature", 0.0)),
        timeout=int(data.get("timeout", 120)),
        max_tokens=int(data.get("max_tokens", 3000)),
        max_retries=max(1, int(data.get("max_retries", 3))),
        cache_path=data.get("cache_path"),
        dry_run=bool(data.get("dry_run", False)),
        n_votes=max(1, int(data.get("n_votes", 1))),
        vote_temperature=float(data.get("vote_temperature", 0.3)),
    )


class LLMClient:
    def __init__(self, config: LLMConfig):
        self.config = config
        self.cache: dict[str, Any] = {}
        self._cache_lock = threading.Lock()
        self._stats_lock = threading.Lock()
        self._stats: dict[str, int] = {
            "cache_hits": 0,
            "api_attempts": 0,
            "api_successes": 0,
            "api_failures": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        self.cache_path = Path(config.cache_path) if config.cache_path else None
        if self.cache_path and self.cache_path.exists():
            for line in self.cache_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                self.cache[row["key"]] = row["response"]

    def chat_json(self, system: str, user: str) -> dict[str, Any]:
        key = self._cache_key(system, user)
        with self._cache_lock:
            cached = self.cache.get(key)
        if cached is not None:
            self._increment_stat("cache_hits")
            return dict(cached)
        if self.config.dry_run:
            result = {
                "gold_status": "uncertain",
                "defect_type": "none",
                "confidence": 0.0,
                "correct_answers": [],
                "needs_expert": True,
                "rationale": "dry_run",
            }
            self._write_cache(key, result)
            return result

        api_key = os.environ.get(self.config.api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing API key environment variable: {self.config.api_key_env}")

        body = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "response_format": {"type": "json_object"},
        }
        invalid_responses = []
        for attempt in range(self.config.max_retries):
            raw = self._post_chat_completions(body, api_key)
            try:
                result = _extract_json_result(raw)
            except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
                invalid_responses.append(_response_diagnostic(raw))
                if attempt + 1 < self.config.max_retries:
                    time.sleep(2**attempt)
                    continue
                raise RuntimeError(
                    "LLM did not return valid JSON after response retries: "
                    f"{invalid_responses}"
                ) from exc
            self._record_usage(raw)
            self._write_cache(key, result)
            return result
        raise RuntimeError("LLM response retry loop ended unexpectedly")

    def _post_chat_completions(self, body: dict[str, Any], api_key: str) -> dict[str, Any]:
        parsed = urlparse(self.config.base_url.rstrip("/") + "/chat/completions")
        conn_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
        context = ssl.create_default_context() if parsed.scheme == "https" else None
        payload = json.dumps(body).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        path = parsed.path or "/chat/completions"
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries):
            conn = (
                conn_cls(parsed.netloc, timeout=self.config.timeout, context=context)
                if context
                else conn_cls(parsed.netloc, timeout=self.config.timeout)
            )
            try:
                self._increment_stat("api_attempts")
                conn.request("POST", path, payload, headers)
                response = conn.getresponse()
                text = response.read().decode("utf-8")
                if 200 <= response.status < 300:
                    parsed_response = json.loads(text)
                    self._increment_stat("api_successes")
                    return parsed_response
                if (
                    response.status in {429, 500, 502, 503, 504}
                    and attempt + 1 < self.config.max_retries
                ):
                    self._increment_stat("api_failures")
                    time.sleep(2**attempt)
                    continue
                self._increment_stat("api_failures")
                raise RuntimeError(f"LLM API error {response.status}: {text}")
            except (OSError, http.client.HTTPException, json.JSONDecodeError) as exc:
                self._increment_stat("api_failures")
                last_error = exc
                if attempt + 1 < self.config.max_retries:
                    time.sleep(2**attempt)
                    continue
            finally:
                conn.close()
        raise RuntimeError(f"LLM API request failed after retries: {last_error}")

    def chat_json_multi(self, system: str, user: str) -> list[dict[str, Any]]:
        """Make n_votes calls at vote_temperature and return all results.

        Falls back to a single chat_json call when n_votes <= 1.  Each voting
        call gets its own cache slot (via _vote_cache_key) so temperature > 0
        produces genuinely different responses across calls.
        """
        if self.config.n_votes <= 1:
            return [self.chat_json(system, user)]
        results = []
        for vi in range(1, self.config.n_votes + 1):
            results.append(self._chat_json_vote(system, user, vi))
        return results

    def chat_json_repeated(self, system: str, user: str, passes: int) -> list[dict[str, Any]]:
        """Run independent, vote-keyed calls for an investigator-style review.

        Unlike ``chat_json_multi``, the number of passes is supplied by the
        caller. This lets a rigorous review use repeated passes without changing
        the voting budget of every other auditor sharing the same config.
        """
        passes = max(int(passes), 1)
        if passes == 1:
            return [self.chat_json(system, user)]
        return [self._chat_json_vote(system, user, index) for index in range(1, passes + 1)]

    def _chat_json_vote(self, system: str, user: str, vote_index: int) -> dict[str, Any]:
        """Single voting call: uses vote_temperature and a vote-specific cache key."""
        key = self._vote_cache_key(system, user, vote_index)
        with self._cache_lock:
            cached = self.cache.get(key)
        if cached is not None:
            self._increment_stat("cache_hits")
            return dict(cached)
        if self.config.dry_run:
            result: dict[str, Any] = {
                "gold_status": "uncertain",
                "defect_type": "none",
                "confidence": 0.0,
                "correct_answers": [],
                "needs_expert": True,
                "rationale": "dry_run",
            }
            self._write_cache(key, result)
            return result

        api_key = os.environ.get(self.config.api_key_env)
        if not api_key:
            raise RuntimeError(
                f"Missing API key environment variable: {self.config.api_key_env}"
            )

        body = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.config.vote_temperature,
            "max_tokens": self.config.max_tokens,
            "response_format": {"type": "json_object"},
        }
        invalid_responses: list[dict[str, Any]] = []
        for attempt in range(self.config.max_retries):
            raw = self._post_chat_completions(body, api_key)
            try:
                result = _extract_json_result(raw)
            except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
                invalid_responses.append(_response_diagnostic(raw))
                if attempt + 1 < self.config.max_retries:
                    time.sleep(2**attempt)
                    continue
                raise RuntimeError(
                    f"LLM vote {vote_index} did not return valid JSON after retries: "
                    f"{invalid_responses}"
                ) from exc
            self._record_usage(raw)
            self._write_cache(key, result)
            return result
        raise RuntimeError("LLM vote retry loop ended unexpectedly")

    def _cache_key(self, system: str, user: str) -> str:
        payload = json.dumps(
            {
                "model": self.config.model,
                "temperature": self.config.temperature,
                "system": system,
                "user": user,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _vote_cache_key(self, system: str, user: str, vote_index: int) -> str:
        payload = json.dumps(
            {
                "model": self.config.model,
                "temperature": self.config.vote_temperature,
                "vote_index": vote_index,
                "system": system,
                "user": user,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _write_cache(self, key: str, response: dict[str, Any]) -> None:
        with self._cache_lock:
            if key in self.cache:
                return
            self.cache[key] = response
            if not self.cache_path:
                return
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with self.cache_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"key": key, "response": response}, ensure_ascii=False) + "\n")

    def _increment_stat(self, key: str, value: int = 1) -> None:
        with self._stats_lock:
            self._stats[key] = self._stats.get(key, 0) + value

    def _record_usage(self, raw: dict[str, Any]) -> None:
        usage = raw.get("usage") if isinstance(raw, dict) else None
        if not isinstance(usage, dict):
            return
        mapping = {
            "prompt_tokens": "prompt_tokens",
            "completion_tokens": "completion_tokens",
            "total_tokens": "total_tokens",
        }
        with self._stats_lock:
            for source, target in mapping.items():
                try:
                    value = int(usage.get(source, 0) or 0)
                except (TypeError, ValueError):
                    value = 0
                self._stats[target] = self._stats.get(target, 0) + value

    def run_stats(self) -> dict[str, Any]:
        """Return reproducibility-safe runtime metadata (never includes API keys)."""
        with self._stats_lock:
            counters = dict(self._stats)
        with self._cache_lock:
            cache_entries = len(self.cache)
        return {
            "model": self.config.model,
            "base_url": self.config.base_url,
            "temperature": self.config.temperature,
            "vote_temperature": self.config.vote_temperature,
            "max_tokens": self.config.max_tokens,
            "configured_votes": self.config.n_votes,
            "cache_path": str(self.cache_path) if self.cache_path else None,
            "cache_entries": cache_entries,
            **counters,
        }


def _extract_json_result(raw: dict[str, Any]) -> dict[str, Any]:
    message = raw["choices"][0]["message"]
    content = message.get("content")
    if isinstance(content, dict):
        return content
    if not isinstance(content, str) or not content.strip():
        raise TypeError("message.content is empty or not text")
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().lower() in {"```", "```json"}:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    result = json.loads(text)
    if not isinstance(result, dict):
        raise TypeError("JSON response is not an object")
    return result


def _response_diagnostic(raw: dict[str, Any]) -> dict[str, Any]:
    try:
        message = raw["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return {"response_shape": str(type(raw)), "response": str(raw)[:500]}
    content = message.get("content")
    return {
        "finish_reason": raw.get("choices", [{}])[0].get("finish_reason"),
        "content_type": type(content).__name__,
        "content_excerpt": str(content)[:300],
        "reasoning_excerpt": str(
            message.get("reasoning")
            or message.get("reasoning_content")
            or ""
        )[:300],
    }
