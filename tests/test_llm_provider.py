"""Unit tests for llm_client provider routing (Fase 8)."""

import pytest

from app.llm_client import get_provider, _hf_endpoint_and_headers


def test_gemini_models_route_to_gemini():
    assert get_provider("gemini-3.5-flash") == "gemini"
    assert get_provider("gemini-3.1-pro-preview") == "gemini"


def test_groq_is_default_provider():
    assert get_provider("llama-3.3-70b-versatile") == "groq"
    assert get_provider("meta-llama/llama-4-scout-17b-16e-instruct") == "groq"
    assert get_provider("qwen/qwen3-32b") == "groq"


def test_hf_prefix_routes_to_self_hosted():
    assert get_provider("hf:username/my-finetuned-model") == "hf"


def test_hf_without_endpoint_raises(monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "hf_endpoint_url", None)
    with pytest.raises(ValueError, match="HF_ENDPOINT_URL"):
        _hf_endpoint_and_headers(None)


def test_hf_endpoint_and_headers(monkeypatch):
    from app.config import get_settings
    cfg = get_settings()
    monkeypatch.setattr(cfg, "hf_endpoint_url", "http://localhost:8000/")
    monkeypatch.setattr(cfg, "hf_api_token", "tok123")

    url, headers = _hf_endpoint_and_headers(None)
    assert url == "http://localhost:8000/v1/chat/completions"
    assert headers["Authorization"] == "Bearer tok123"

    # Explicit api_key overrides the configured token
    _, headers2 = _hf_endpoint_and_headers("override")
    assert headers2["Authorization"] == "Bearer override"
