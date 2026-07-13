import tempfile
import unittest
from pathlib import Path
from unittest import mock

from benchcore.llm_client import LLMClient, LLMConfig, _extract_json_result


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

    def _post_chat_completions(self, body, api_key):
        self.calls += 1
        return self.responses.pop(0)


class LLMClientTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
