import json
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

from benchcore.llm_client import (
    LLMClient,
    LLMConfig,
    _extract_json_result,
    _perform_http_request_with_deadline,
)


class StubLLMClient(LLMClient):
    def __init__(self, responses):
        super().__init__(
            LLMConfig(
                model="stub",
                base_url="https://example.invalid",
                api_key_env="STUB_API_KEY",
                max_retries=2,
            )
        )
        self.responses = list(responses)
        self.calls = 0
        self.bodies = []

    def _post_chat_completions(self, body, api_key):
        # The real transport accounts/enforces a provider attempt before I/O.
        # This stub bypasses that transport, so mirror the same boundary.
        self._begin_api_attempt()
        self.calls += 1
        self.bodies.append(body)
        return self.responses.pop(0)


class CacheOnlyProbeClient(LLMClient):
    def __init__(self, cache_path: Path):
        super().__init__(LLMConfig(
            model="cache-only", base_url="https://example.invalid",
            api_key_env="STUB_API_KEY", cache_path=str(cache_path), cache_only=True,
        ))
        self.transport_called = False

    def _post_chat_completions(self, body, api_key):
        self.transport_called = True
        raise AssertionError("cache-only mode must refuse before transport")


class BlockingLLMClient(LLMClient):
    """Keeps the leader in-flight until every intended follower is waiting."""

    def __init__(self, cache_path: Path, *, failure: Exception | None = None):
        super().__init__(LLMConfig(
            model="blocking",
            base_url="https://example.invalid",
            api_key_env="STUB_API_KEY",
            max_retries=1,
            cache_path=str(cache_path),
        ))
        self.failure = failure
        self.entered = threading.Event()
        self.release = threading.Event()
        self._calls_lock = threading.Lock()
        self.calls = 0

    def _post_chat_completions(self, body, api_key):
        with self._calls_lock:
            self.calls += 1
        self.entered.set()
        if not self.release.wait(timeout=5):
            raise TimeoutError("test did not release the single-flight leader")
        if self.failure is not None:
            raise self.failure
        return {
            "choices": [{"message": {"content": '{"status":"ok"}'}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 2, "total_tokens": 9},
        }


class DistinctKeyLLMClient(LLMClient):
    """A barrier proves unrelated keys are not serialized behind one flight."""

    def __init__(self, cache_path: Path):
        super().__init__(LLMConfig(
            model="distinct",
            base_url="https://example.invalid",
            api_key_env="STUB_API_KEY",
            max_retries=1,
            cache_path=str(cache_path),
        ))
        self.barrier = threading.Barrier(2)
        self._calls_lock = threading.Lock()
        self.calls = 0

    def _post_chat_completions(self, body, api_key):
        with self._calls_lock:
            self.calls += 1
        self.barrier.wait(timeout=3)
        user = body["messages"][1]["content"]
        return {
            "choices": [{"message": {"content": json.dumps({"user": user})}}],
        }


def _wait_for_singleflight_followers(
    client: LLMClient,
    expected: int,
    *,
    timeout: float = 3,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if client.run_stats()["singleflight_waits"] >= expected:
            return
        time.sleep(0.005)
    raise AssertionError(
        f"only {client.run_stats()['singleflight_waits']} of {expected} followers joined"
    )


class LLMClientTest(unittest.TestCase):
    def test_cache_only_refuses_miss_before_network_and_uses_exact_hit(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "cache.jsonl"
            client = CacheOnlyProbeClient(cache_path)
            with self.assertRaisesRegex(RuntimeError, "cache-only replay missed"):
                client.chat_json("system", "uncached")
            self.assertFalse(client.transport_called)
            cache_path.write_text(
                json.dumps({
                    "key": client._cache_key("system", "cached"),
                    "response": {"status": "cached"},
                }) + "\n",
                encoding="utf-8",
            )
            cached = CacheOnlyProbeClient(cache_path)
            self.assertEqual(cached.chat_json("system", "cached"), {"status": "cached"})
            self.assertFalse(cached.transport_called)

    def test_transaction_deadline_covers_stalled_first_byte(self):
        entered = threading.Event()
        released = threading.Event()

        class StalledConnection:
            def request(self, *args):
                return None

            def getresponse(self):
                entered.set()
                released.wait(timeout=5)
                raise OSError("connection closed")

            def close(self):
                released.set()

        started = time.monotonic()
        with self.assertRaisesRegex(TimeoutError, "HTTP transaction exceeded"):
            _perform_http_request_with_deadline(
                StalledConnection(), "POST", "/", b"{}", {}, 0.03
            )
        self.assertTrue(entered.is_set())
        self.assertLess(time.monotonic() - started, 0.5)

    def test_transaction_deadline_covers_stalled_response_body(self):
        entered = threading.Event()
        released = threading.Event()

        class BlockingResponse:
            status = 200

            def read(self):
                entered.set()
                released.wait(timeout=5)
                return b"{}"

        class ClosingConnection:
            def __init__(self):
                self.closed = False
                self.closed_event = threading.Event()

            def request(self, *args):
                return None

            def getresponse(self):
                return BlockingResponse()

            def close(self):
                self.closed = True
                released.set()
                self.closed_event.set()

        conn = ClosingConnection()
        started = time.monotonic()
        with self.assertRaisesRegex(TimeoutError, "HTTP transaction exceeded"):
            _perform_http_request_with_deadline(
                conn, "POST", "/", b"{}", {}, 0.03
            )
        self.assertTrue(entered.is_set())
        self.assertTrue(conn.closed_event.wait(timeout=0.5))
        self.assertTrue(conn.closed)
        self.assertLess(time.monotonic() - started, 0.5)

    def test_optional_thinking_mode_is_sent_and_part_of_reproducibility(self):
        client = StubLLMClient([
            {"choices": [{"message": {"content": '{"status":"ok"}'}}]},
        ])
        client.config.thinking = "disabled"
        with tempfile.TemporaryDirectory() as tmp:
            client.cache_path = Path(tmp) / "cache.jsonl"
            with mock.patch.dict("os.environ", {"STUB_API_KEY": "test"}):
                self.assertEqual(client.chat_json("system", "user"), {"status": "ok"})

        self.assertEqual(client.bodies[0]["thinking"], {"type": "disabled"})
        self.assertEqual(client.run_stats()["thinking"], "disabled")

    def test_truncated_json_fails_fast_without_identical_provider_retry(self):
        client = StubLLMClient([
            {
                "choices": [{
                    "finish_reason": "length",
                    # A prefix can be valid JSON and still be provider-marked
                    # truncated; finish_reason must take precedence over parse.
                    "message": {"content": '{"status":"partial"}'},
                }],
                "usage": {"prompt_tokens": 4, "completion_tokens": 8, "total_tokens": 12},
            },
            {"choices": [{"message": {"content": '{"status":"ok"}'}}]},
        ])
        with tempfile.TemporaryDirectory() as tmp:
            client.cache_path = Path(tmp) / "cache.jsonl"
            with mock.patch.dict("os.environ", {"STUB_API_KEY": "test"}):
                with self.assertRaisesRegex(RuntimeError, "truncated"):
                    client.chat_json("system", "user")

        self.assertEqual(client.calls, 1)
        self.assertEqual(client.run_stats()["truncated_responses"], 1)
        self.assertEqual(client.run_stats()["total_tokens"], 12)

    def test_api_and_observed_token_budgets_block_later_provider_calls(self):
        response = {
            "choices": [{"message": {"content": '{"status":"ok"}'}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 2, "total_tokens": 9},
        }
        attempts = StubLLMClient([response, response])
        attempts.config.max_api_attempts = 1
        with tempfile.TemporaryDirectory() as tmp:
            attempts.cache_path = Path(tmp) / "attempts.jsonl"
            with mock.patch.dict("os.environ", {"STUB_API_KEY": "test"}):
                self.assertEqual(attempts.chat_json("s", "first"), {"status": "ok"})
                with self.assertRaisesRegex(RuntimeError, "API-attempt budget"):
                    attempts.chat_json("s", "second")
        self.assertEqual(attempts.calls, 1)

        response_without_total = {
            "choices": [{"message": {"content": '{"status":"ok"}'}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 2},
        }
        tokens = StubLLMClient([response_without_total, response_without_total])
        tokens.config.observed_token_stop = 8
        with tempfile.TemporaryDirectory() as tmp:
            tokens.cache_path = Path(tmp) / "tokens.jsonl"
            with mock.patch.dict("os.environ", {"STUB_API_KEY": "test"}):
                self.assertEqual(tokens.chat_json("s", "first"), {"status": "ok"})
                with self.assertRaisesRegex(RuntimeError, "observed-token stop"):
                    tokens.chat_json("s", "second")
        self.assertEqual(tokens.calls, 1)

    def test_extracts_fenced_json(self):
        result = _extract_json_result(
            {
                "choices": [
                    {
                        "message": {
                            "content": "```json\n{\"status\": \"ok\"}\n```"
                        }
                    }
                ]
            }
        )
        self.assertEqual(result, {"status": "ok"})

    def test_retries_null_content(self):
        client = StubLLMClient(
            [
                {
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"content": None},
                        }
                    ]
                },
                {
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"content": "{\"status\": \"ok\"}"},
                        }
                    ]
                },
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            client.cache_path = Path(tmp) / "cache.jsonl"
            with mock.patch.dict("os.environ", {"STUB_API_KEY": "test"}):
                result = client.chat_json("system", "user")
        self.assertEqual(result, {"status": "ok"})
        self.assertEqual(client.calls, 2)

    def test_invalid_json_attempts_are_included_in_token_accounting(self):
        client = StubLLMClient(
            [
                {
                    "choices": [{"message": {"content": None}}],
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                        "total_tokens": 15,
                    },
                },
                {
                    "choices": [{"message": {"content": '{"status":"ok"}'}}],
                    "usage": {
                        "prompt_tokens": 11,
                        "completion_tokens": 2,
                        "total_tokens": 13,
                    },
                },
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            client.cache_path = Path(tmp) / "cache.jsonl"
            with mock.patch.dict("os.environ", {"STUB_API_KEY": "test"}):
                self.assertEqual(client.chat_json("system", "user"), {"status": "ok"})
        stats = client.run_stats()
        self.assertEqual(stats["prompt_tokens"], 21)
        self.assertEqual(stats["completion_tokens"], 7)
        self.assertEqual(stats["total_tokens"], 28)

    def test_repeated_calls_use_independent_vote_slots_and_record_usage(self):
        client = StubLLMClient(
            [
                {
                    "choices": [{"message": {"content": '{"verdict":"likely_true"}'}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
                },
                {
                    "choices": [{"message": {"content": '{"verdict":"false_positive"}'}}],
                    "usage": {"prompt_tokens": 11, "completion_tokens": 3, "total_tokens": 14},
                },
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            client.cache_path = Path(tmp) / "cache.jsonl"
            with mock.patch.dict("os.environ", {"STUB_API_KEY": "test"}):
                results = client.chat_json_repeated("system", "user", 2)

        self.assertEqual([row["verdict"] for row in results], ["likely_true", "false_positive"])
        stats = client.run_stats()
        self.assertEqual(client.calls, 2)
        self.assertEqual(stats["prompt_tokens"], 21)
        self.assertEqual(stats["total_tokens"], 26)

    def test_same_key_concurrency_issues_one_request_and_one_cache_record(self):
        workers = 16
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "cache.jsonl"
            client = BlockingLLMClient(cache_path)
            start = threading.Barrier(workers)

            def invoke():
                start.wait(timeout=3)
                return client.chat_json("same-system", "same-user")

            with mock.patch.dict("os.environ", {"STUB_API_KEY": "test"}):
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futures = [pool.submit(invoke) for _ in range(workers)]
                    self.assertTrue(client.entered.wait(timeout=3))
                    try:
                        _wait_for_singleflight_followers(client, workers - 1)
                    finally:
                        client.release.set()
                    results = [future.result(timeout=3) for future in futures]

                # A later call preserves the ordinary persistent-cache behavior.
                cached = client.chat_json("same-system", "same-user")

            self.assertEqual(client.calls, 1)
            self.assertEqual(results, [{"status": "ok"}] * workers)
            self.assertEqual(cached, {"status": "ok"})
            records = [
                json.loads(line)
                for line in cache_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(records), 1)
            stats = client.run_stats()
            self.assertEqual(stats["singleflight_waits"], workers - 1)
            self.assertEqual(stats["singleflight_shared_results"], workers - 1)
            self.assertEqual(stats["singleflight_shared_failures"], 0)
            self.assertEqual(stats["cache_hits"], 1)
            self.assertEqual(stats["prompt_tokens"], 7)
            self.assertEqual(stats["total_tokens"], 9)

    def test_same_key_waiters_share_exception_and_failure_is_not_cached(self):
        workers = 12
        shared_failure = RuntimeError("synthetic provider failure")
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "cache.jsonl"
            client = BlockingLLMClient(cache_path, failure=shared_failure)
            start = threading.Barrier(workers)

            def invoke():
                start.wait(timeout=3)
                try:
                    client.chat_json("same-system", "same-failing-user")
                except Exception as exc:  # return it so identity can be checked
                    return exc
                raise AssertionError("the synthetic failure unexpectedly succeeded")

            with mock.patch.dict("os.environ", {"STUB_API_KEY": "test"}):
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futures = [pool.submit(invoke) for _ in range(workers)]
                    self.assertTrue(client.entered.wait(timeout=3))
                    try:
                        _wait_for_singleflight_followers(client, workers - 1)
                    finally:
                        client.release.set()
                    failures = [future.result(timeout=3) for future in futures]

                # Failed flights are not negative-cache entries; the next call retries.
                with self.assertRaisesRegex(RuntimeError, "synthetic provider failure"):
                    client.chat_json("same-system", "same-failing-user")

            self.assertEqual(client.calls, 2)
            self.assertEqual({id(exc) for exc in failures}, {id(shared_failure)})
            self.assertTrue(all(str(exc) == "synthetic provider failure" for exc in failures))
            self.assertFalse(cache_path.exists())
            stats = client.run_stats()
            self.assertEqual(stats["singleflight_waits"], workers - 1)
            self.assertEqual(stats["singleflight_shared_failures"], workers - 1)
            self.assertEqual(stats["singleflight_shared_results"], 0)

    def test_cache_write_failure_is_shared_and_never_publishes_memory_cache(self):
        workers = 6
        with tempfile.TemporaryDirectory() as tmp:
            invalid_parent = Path(tmp) / "not-a-directory"
            invalid_parent.write_text("blocks cache directory creation", encoding="utf-8")
            client = BlockingLLMClient(invalid_parent / "cache.jsonl")
            start = threading.Barrier(workers)

            def invoke():
                start.wait(timeout=3)
                try:
                    client.chat_json("system", "cache-write-failure")
                except Exception as exc:
                    return exc
                raise AssertionError("cache write unexpectedly succeeded")

            with mock.patch.dict("os.environ", {"STUB_API_KEY": "test"}):
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futures = [pool.submit(invoke) for _ in range(workers)]
                    self.assertTrue(client.entered.wait(timeout=3))
                    try:
                        _wait_for_singleflight_followers(client, workers - 1)
                    finally:
                        client.release.set()
                    failures = [future.result(timeout=3) for future in futures]

            self.assertEqual(client.calls, 1)
            self.assertEqual(len({id(exc) for exc in failures}), 1)
            self.assertTrue(all(isinstance(exc, OSError) for exc in failures))
            self.assertEqual(client.cache, {})
            self.assertEqual(
                client.run_stats()["singleflight_shared_failures"],
                workers - 1,
            )

    def test_distinct_keys_and_vote_slots_execute_independently(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "cache.jsonl"
            client = DistinctKeyLLMClient(cache_path)
            with mock.patch.dict("os.environ", {"STUB_API_KEY": "test"}):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    left = pool.submit(client.chat_json, "system", "left")
                    right = pool.submit(client.chat_json, "system", "right")
                    self.assertEqual(left.result(timeout=3), {"user": "left"})
                    self.assertEqual(right.result(timeout=3), {"user": "right"})

            self.assertEqual(client.calls, 2)
            self.assertEqual(client.run_stats()["singleflight_waits"], 0)
            records = [
                json.loads(line)
                for line in cache_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len({row["key"] for row in records}), 2)

        # Vote index is part of the key, so two slots may also proceed in parallel.
        with tempfile.TemporaryDirectory() as tmp:
            client = DistinctKeyLLMClient(Path(tmp) / "votes.jsonl")
            with mock.patch.dict("os.environ", {"STUB_API_KEY": "test"}):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    first = pool.submit(client._chat_json_vote, "system", "vote", 1)
                    second = pool.submit(client._chat_json_vote, "system", "vote", 2)
                    self.assertEqual(first.result(timeout=3), {"user": "vote"})
                    self.assertEqual(second.result(timeout=3), {"user": "vote"})
            self.assertEqual(client.calls, 2)

    def test_same_vote_key_is_also_single_flight(self):
        workers = 8
        with tempfile.TemporaryDirectory() as tmp:
            client = BlockingLLMClient(Path(tmp) / "votes.jsonl")
            start = threading.Barrier(workers)

            def invoke():
                start.wait(timeout=3)
                return client._chat_json_vote("system", "same-vote", 2)

            with mock.patch.dict("os.environ", {"STUB_API_KEY": "test"}):
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futures = [pool.submit(invoke) for _ in range(workers)]
                    self.assertTrue(client.entered.wait(timeout=3))
                    try:
                        _wait_for_singleflight_followers(client, workers - 1)
                    finally:
                        client.release.set()
                    results = [future.result(timeout=3) for future in futures]

            self.assertEqual(client.calls, 1)
            self.assertEqual(results, [{"status": "ok"}] * workers)
            self.assertEqual(client.run_stats()["singleflight_waits"], workers - 1)


if __name__ == "__main__":
    unittest.main()
