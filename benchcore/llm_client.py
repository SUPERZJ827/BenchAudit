from __future__ import annotations

import hashlib
import http.client
import json
import os
import ssl
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
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
    # Some OpenAI-compatible providers expose a thinking-mode toggle.  Keep it
    # opt-in so providers that do not implement the extension never receive an
    # unknown request field.  Constrained schema projection normally benefits
    # from the cheaper, less verbose non-thinking mode.
    thinking: str | None = None
    max_api_attempts: int | None = None
    # Soft stop based on usage already reported by the provider.  It is not a
    # hard reservation: one in-flight request may cross it, and providers that
    # omit usage cannot be governed by this counter.  ``max_api_attempts`` is
    # the exact cross-thread request ceiling.
    observed_token_stop: int | None = None
    # Reproducibility replays may stage a prior cache.  In that mode a cache
    # miss is an invalid experiment, never permission to silently buy a fresh
    # model sample.
    cache_only: bool = False


@dataclass(frozen=True)
class _InFlight:
    future: Future[dict[str, Any]]
    owner_thread_id: int


_CACHE_MISS = object()


def _close_connection_async(conn: http.client.HTTPConnection) -> None:
    """Request connection teardown without letting a broken TLS close block us."""
    threading.Thread(
        target=conn.close,
        name="llm-http-connection-closer",
        daemon=True,
    ).start()


def _perform_http_request_with_deadline(
    conn: http.client.HTTPConnection,
    method: str,
    path: str,
    payload: bytes,
    headers: dict[str, str],
    timeout: float,
) -> tuple[int, bytes]:
    """Bound the complete HTTP transaction, including first-byte wait.

    Socket timeouts alone are per low-level operation.  In particular, a
    provider can stall while sending the response headers, before there is an
    ``HTTPResponse`` object for the body-only deadline to guard.  Keeping the
    whole transaction in one daemon worker gives the caller one honest
    wall-clock bound.  The connection is closed asynchronously on expiry for
    the same asynchronous-close policy used by the request path.
    """
    if timeout <= 0:
        raise ValueError("request deadline must be positive")
    done = threading.Event()
    outcome: dict[str, Any] = {}

    def transact() -> None:
        try:
            conn.request(method, path, payload, headers)
            response = conn.getresponse()
            outcome["status"] = response.status
            outcome["body"] = response.read()
        except BaseException as exc:
            outcome["exception"] = exc
        finally:
            done.set()

    worker = threading.Thread(target=transact, name="llm-http-transaction", daemon=True)
    worker.start()
    if not done.wait(timeout=timeout):
        _close_connection_async(conn)
        raise TimeoutError(f"LLM HTTP transaction exceeded the {timeout:.1f}s wall-clock deadline")
    if "exception" in outcome:
        raise outcome["exception"]
    status, body = outcome.get("status"), outcome.get("body")
    if not isinstance(status, int) or not isinstance(body, bytes):
        raise http.client.HTTPException("LLM HTTP transaction returned invalid data")
    return status, body


def load_llm_config(path: str | None = None) -> LLMConfig:
    data: dict[str, Any] = {}
    if path:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    thinking = data.get("thinking")
    if thinking not in {None, "enabled", "disabled"}:
        raise ValueError("thinking must be 'enabled', 'disabled', or omitted")
    max_api_attempts = _optional_positive_int(
        data.get("max_api_attempts"), name="max_api_attempts"
    )
    observed_token_stop = _optional_positive_int(
        data.get("observed_token_stop"), name="observed_token_stop"
    )
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
        thinking=thinking,
        max_api_attempts=max_api_attempts,
        observed_token_stop=observed_token_stop,
    )


class LLMClient:
    def __init__(self, config: LLMConfig):
        self.config = config
        self.cache: dict[str, Any] = {}
        self._cache_lock = threading.Lock()
        self._inflight: dict[str, _InFlight] = {}
        self._stats_lock = threading.Lock()
        self._stats: dict[str, int] = {
            "cache_hits": 0,
            "singleflight_waits": 0,
            "singleflight_shared_results": 0,
            "singleflight_shared_failures": 0,
            "api_attempts": 0,
            "api_successes": 0,
            "api_failures": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "invalid_responses": 0,
            "truncated_responses": 0,
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
        return self._singleflight_json(
            key,
            lambda: self._chat_json_uncached(system, user, key),
        )

    def _chat_json_uncached(
        self,
        system: str,
        user: str,
        key: str,
    ) -> dict[str, Any]:
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

        if self.config.cache_only:
            raise RuntimeError(
                "cache-only replay missed an exact request key; refusing HTTP execution"
            )

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
        if self.config.thinking is not None:
            body["thinking"] = {"type": self.config.thinking}
        invalid_responses = []
        for attempt in range(self.config.max_retries):
            raw = self._post_chat_completions(body, api_key)
            # A provider response consumes tokens even when its JSON payload is
            # malformed or truncated.  Cost/accounting gates must include those
            # failed attempts rather than recording only the eventual success.
            self._record_usage(raw)
            diagnostic = _response_diagnostic(raw)
            if diagnostic.get("finish_reason") == "length":
                self._increment_stat("invalid_responses")
                self._increment_stat("truncated_responses")
                raise RuntimeError(
                    "LLM JSON response was truncated; refusing an identical "
                    f"blind retry: {diagnostic}"
                )
            try:
                result = _extract_json_result(raw)
            except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
                invalid_responses.append(diagnostic)
                self._increment_stat("invalid_responses")
                if attempt + 1 < self.config.max_retries:
                    time.sleep(2**attempt)
                    continue
                raise RuntimeError(
                    "LLM did not return valid JSON after response retries: "
                    f"{invalid_responses}"
                ) from exc
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
                self._begin_api_attempt()
                status, response_body = _perform_http_request_with_deadline(
                    conn, "POST", path, payload, headers, float(self.config.timeout)
                )
                text = response_body.decode("utf-8")
                if 200 <= status < 300:
                    parsed_response = json.loads(text)
                    self._increment_stat("api_successes")
                    return parsed_response
                if (
                    status in {429, 500, 502, 503, 504}
                    and attempt + 1 < self.config.max_retries
                ):
                    self._increment_stat("api_failures")
                    time.sleep(2**attempt)
                    continue
                self._increment_stat("api_failures")
                raise RuntimeError(f"LLM API error {status}: {text}")
            except (OSError, http.client.HTTPException, json.JSONDecodeError) as exc:
                self._increment_stat("api_failures")
                last_error = exc
                if attempt + 1 < self.config.max_retries:
                    time.sleep(2**attempt)
                    continue
            finally:
                # ``HTTPConnection.close`` can itself wait on a TLS/socket
                # state transition.  The response deadline would be illusory
                # if cleanup ran synchronously on the request path.
                _close_connection_async(conn)
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
        return self._singleflight_json(
            key,
            lambda: self._chat_json_vote_uncached(system, user, vote_index, key),
        )

    def _chat_json_vote_uncached(
        self,
        system: str,
        user: str,
        vote_index: int,
        key: str,
    ) -> dict[str, Any]:
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

        if self.config.cache_only:
            raise RuntimeError(
                "cache-only replay missed an exact vote request key; refusing HTTP execution"
            )

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
        if self.config.thinking is not None:
            body["thinking"] = {"type": self.config.thinking}
        invalid_responses: list[dict[str, Any]] = []
        for attempt in range(self.config.max_retries):
            raw = self._post_chat_completions(body, api_key)
            self._record_usage(raw)
            diagnostic = _response_diagnostic(raw)
            if diagnostic.get("finish_reason") == "length":
                self._increment_stat("invalid_responses")
                self._increment_stat("truncated_responses")
                raise RuntimeError(
                    f"LLM vote {vote_index} JSON response was truncated; "
                    f"refusing an identical blind retry: {diagnostic}"
                )
            try:
                result = _extract_json_result(raw)
            except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
                invalid_responses.append(diagnostic)
                self._increment_stat("invalid_responses")
                if attempt + 1 < self.config.max_retries:
                    time.sleep(2**attempt)
                    continue
                raise RuntimeError(
                    f"LLM vote {vote_index} did not return valid JSON after retries: "
                    f"{invalid_responses}"
                ) from exc
            self._write_cache(key, result)
            return result
        raise RuntimeError("LLM vote retry loop ended unexpectedly")

    def _singleflight_json(
        self,
        key: str,
        operation: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        """Run at most one concurrent operation for a cache key.

        The cache lookup and flight registration are one atomic critical
        section. Followers wait outside the lock and observe the leader's exact
        result or failure. Failed calls are deliberately not cached: callers
        arriving after the failed flight has ended may retry normally.
        """

        thread_id = threading.get_ident()
        cached: Any = _CACHE_MISS
        with self._cache_lock:
            if key in self.cache:
                cached = self.cache[key]
                flight = None
                leader = False
            else:
                flight = self._inflight.get(key)
                if flight is None:
                    flight = _InFlight(
                        future=Future(),
                        owner_thread_id=thread_id,
                    )
                    self._inflight[key] = flight
                    leader = True
                else:
                    leader = False

        if cached is not _CACHE_MISS:
            self._increment_stat("cache_hits")
            return dict(cached)
        assert flight is not None
        if not leader:
            if flight.owner_thread_id == thread_id:
                raise RuntimeError(
                    "recursive LLM request for the same cache key would deadlock"
                )
            self._increment_stat("singleflight_waits")
            try:
                shared = flight.future.result()
            except BaseException:
                self._increment_stat("singleflight_shared_failures")
                raise
            self._increment_stat("singleflight_shared_results")
            return dict(shared)

        try:
            result = operation()
            if not isinstance(result, dict):
                raise TypeError(
                    "single-flight LLM operation must return a JSON object"
                )
        except BaseException as exc:
            self._finish_flight(key, flight, exception=exc)
            raise
        self._finish_flight(key, flight, result=result)
        return dict(result)

    def _finish_flight(
        self,
        key: str,
        flight: "_InFlight",
        *,
        result: dict[str, Any] | None = None,
        exception: BaseException | None = None,
    ) -> None:
        """Publish one terminal flight outcome and remove only that flight."""

        if (result is None) == (exception is None):
            raise ValueError("exactly one flight result or exception is required")
        if exception is not None:
            flight.future.set_exception(exception)
        else:
            flight.future.set_result(result)
        with self._cache_lock:
            if self._inflight.get(key) is flight:
                del self._inflight[key]

    def _cache_key(self, system: str, user: str) -> str:
        payload = json.dumps(
            {
                "model": self.config.model,
                "base_url": self.config.base_url.rstrip("/"),
                "temperature": self.config.temperature,
                "max_tokens": self.config.max_tokens,
                "dry_run": self.config.dry_run,
                "response_format": "json_object",
                "thinking": self.config.thinking,
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
                "base_url": self.config.base_url.rstrip("/"),
                "temperature": self.config.vote_temperature,
                "max_tokens": self.config.max_tokens,
                "dry_run": self.config.dry_run,
                "response_format": "json_object",
                "thinking": self.config.thinking,
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
            # Publish to memory only after the persistent-cache append succeeds.
            # Otherwise a concurrent caller could observe a cache hit while the
            # leader and its already-waiting followers receive a write error.
            if self.cache_path:
                self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                with self.cache_path.open("a", encoding="utf-8") as f:
                    f.write(
                        json.dumps(
                            {"key": key, "response": response},
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
            self.cache[key] = dict(response)

    def _increment_stat(self, key: str, value: int = 1) -> None:
        with self._stats_lock:
            self._stats[key] = self._stats.get(key, 0) + value

    def _begin_api_attempt(self) -> None:
        """Enforce an exact call cap and a clearly named observed-usage stop."""

        with self._stats_lock:
            attempts = self._stats.get("api_attempts", 0)
            total_tokens = self._stats.get("total_tokens", 0)
            if (
                self.config.max_api_attempts is not None
                and attempts >= self.config.max_api_attempts
            ):
                raise RuntimeError(
                    "LLM API-attempt budget exhausted before provider call "
                    f"({attempts}/{self.config.max_api_attempts})"
                )
            if (
                self.config.observed_token_stop is not None
                and total_tokens >= self.config.observed_token_stop
            ):
                raise RuntimeError(
                    "LLM observed-token stop reached before provider call "
                    f"({total_tokens}/{self.config.observed_token_stop})"
                )
            self._stats["api_attempts"] = attempts + 1

    def _record_usage(self, raw: dict[str, Any]) -> None:
        usage = raw.get("usage") if isinstance(raw, dict) else None
        if not isinstance(usage, dict):
            return
        def parsed(name: str) -> int:
            try:
                return max(0, int(usage.get(name, 0) or 0))
            except (TypeError, ValueError):
                return 0

        prompt_tokens = parsed("prompt_tokens")
        completion_tokens = parsed("completion_tokens")
        if "total_tokens" in usage:
            total_tokens = parsed("total_tokens")
        else:
            total_tokens = prompt_tokens + completion_tokens
        with self._stats_lock:
            self._stats["prompt_tokens"] += prompt_tokens
            self._stats["completion_tokens"] += completion_tokens
            self._stats["total_tokens"] += total_tokens

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
            "thinking": self.config.thinking,
            "max_api_attempts": self.config.max_api_attempts,
            "observed_token_stop": self.config.observed_token_stop,
            "observed_token_stop_semantics": (
                "soft stop after provider-reported usage; not a concurrent hard cap"
            ),
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
        return {"response_shape": str(type(raw))}
    content = message.get("content")
    reasoning = message.get("reasoning") or message.get("reasoning_content")
    return {
        "finish_reason": raw.get("choices", [{}])[0].get("finish_reason"),
        "content_type": type(content).__name__,
        "content_chars": len(content) if isinstance(content, str) else None,
        "reasoning_chars": len(reasoning) if isinstance(reasoning, str) else None,
    }


def _optional_positive_int(value: Any, *, name: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{name} must be a positive integer or omitted")
    return value
