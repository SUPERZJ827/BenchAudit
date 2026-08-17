from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchcore.llm_client import LLMClient, LLMConfig, load_llm_config


def client(**kwargs) -> LLMClient:
    return LLMClient(LLMConfig(model="m", base_url="https://example.invalid", **kwargs))


def body_for(**kwargs) -> dict:
    body: dict = {}
    client(**kwargs)._apply_thinking(body)
    return body


def test_deepseek_style_sends_the_thinking_field() -> None:
    assert body_for(thinking="enabled") == {"thinking": {"type": "enabled"}}
    assert body_for(thinking="disabled") == {"thinking": {"type": "disabled"}}


def test_openrouter_style_sends_the_reasoning_field_instead() -> None:
    assert body_for(thinking="enabled", thinking_style="openrouter") == {"reasoning": {"enabled": True}}
    assert body_for(thinking="disabled", thinking_style="openrouter") == {"reasoning": {"enabled": False}}


def test_no_toggle_is_sent_when_thinking_is_unset() -> None:
    assert body_for() == {}
    assert body_for(thinking_style="openrouter") == {}


def test_default_style_keeps_cache_keys_byte_identical() -> None:
    # Frozen caches were written before this field existed; a default-style run
    # must still hash to the same key or every replay would re-call the API.
    baseline = client(thinking="enabled")._cache_key("sys", "usr")
    assert client(thinking="enabled", thinking_style="deepseek")._cache_key("sys", "usr") == baseline


def test_non_default_style_changes_the_cache_key() -> None:
    deepseek = client(thinking="enabled")._cache_key("sys", "usr")
    openrouter = client(thinking="enabled", thinking_style="openrouter")._cache_key("sys", "usr")
    assert deepseek != openrouter


def test_config_rejects_an_unknown_style(tmp_path: Path) -> None:
    path = tmp_path / "cfg.json"
    path.write_text(json.dumps({"thinking_style": "anthropic"}), encoding="utf-8")
    with pytest.raises(ValueError, match="thinking_style"):
        load_llm_config(str(path))


def test_config_round_trips_a_known_style(tmp_path: Path) -> None:
    path = tmp_path / "cfg.json"
    path.write_text(json.dumps({"thinking": "enabled", "thinking_style": "openrouter"}), encoding="utf-8")
    config = load_llm_config(str(path))
    assert config.thinking_style == "openrouter"
    assert load_llm_config().thinking_style == "deepseek"
