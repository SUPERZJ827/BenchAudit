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


if __name__ == "__main__":
    unittest.main()
