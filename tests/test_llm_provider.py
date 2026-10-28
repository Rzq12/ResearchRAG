"""Unit tests for llm_client provider routing (Fase 8)."""

import httpx
import pytest

from app.llm_client import (
    _hf_endpoint_and_headers,
    _openai_endpoint_and_headers,
    call_llm,
    friendly_llm_error,
    get_provider,
    resolve_api_key,
    stream_llm,
)


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


# ─── User-supplied OpenAI-compatible endpoints ("openai:" prefix) ─────────────

def _route_httpx(monkeypatch, handler):
    """Send every httpx.Client request in llm_client to `handler`."""
    real_client = httpx.Client
    monkeypatch.setattr(
        httpx, "Client",
        lambda *a, **k: real_client(*a, transport=httpx.MockTransport(handler), **k),
    )


def test_openai_prefix_routes_to_custom_provider():
    assert get_provider("openai:gpt-4o-mini") == "openai"
    # Groq-hosted OpenAI models use a slash, not the colon prefix.
    assert get_provider("openai/gpt-oss-120b") == "groq"


@pytest.mark.parametrize("base_url, expected", [
    ("https://api.openai.com/v1", "https://api.openai.com/v1/chat/completions"),
    ("http://localhost:11434/v1/", "http://localhost:11434/v1/chat/completions"),
    ("https://x.ai/v1/chat/completions", "https://x.ai/v1/chat/completions"),
])
def test_openai_endpoint_builds_chat_completions_url(base_url, expected):
    url, _ = _openai_endpoint_and_headers(base_url, "sk-test")
    assert url == expected


def test_openai_endpoint_without_key_sends_no_auth_header():
    _, headers = _openai_endpoint_and_headers("http://localhost:11434/v1", None)
    assert "Authorization" not in headers


def test_openai_endpoint_without_base_url_raises():
    with pytest.raises(ValueError, match="base URL"):
        _openai_endpoint_and_headers(None, "sk-test")


def test_resolve_api_key_never_leaks_server_key_to_custom_endpoint(monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "groq_api_key", "server-secret")
    assert resolve_api_key("openai", None) is None
    assert resolve_api_key("openai", "user-key") == "user-key"


def test_resolve_api_key_falls_back_to_same_provider_only(monkeypatch):
    from app.config import get_settings
    cfg = get_settings()
    monkeypatch.setattr(cfg, "groq_api_key", "groq-secret")
    monkeypatch.setattr(cfg, "gemini_api_key", "gemini-secret")
    assert resolve_api_key("gemini", None) == "gemini-secret"
    assert resolve_api_key("groq", None) == "groq-secret"


def test_call_llm_openai_posts_to_user_endpoint(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("Authorization")
        seen["body"] = request.read().decode()
        return httpx.Response(200, json={"choices": [{"message": {"content": "hello"}}]})

    _route_httpx(monkeypatch, handler)
    out = call_llm(
        "openai:gpt-4o-mini", [{"role": "user", "content": "hi"}], "sk-user",
        base_url="https://api.example.com/v1",
    )

    assert out == "hello"
    assert seen["url"] == "https://api.example.com/v1/chat/completions"
    assert seen["auth"] == "Bearer sk-user"
    assert '"model":"gpt-4o-mini"' in seen["body"].replace(" ", "")


def test_stream_llm_openai_skips_usage_frames(monkeypatch):
    sse = (
        'data: {"choices":[{"delta":{"content":"Hel"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"lo"}}]}\n\n'
        'data: {"choices":[],"usage":{"total_tokens":3}}\n\n'
        "data: [DONE]\n\n"
    )
    _route_httpx(monkeypatch, lambda request: httpx.Response(200, text=sse))

    tokens = list(stream_llm(
        "openai:llama3.1", [{"role": "user", "content": "hi"}], None,
        base_url="http://localhost:11434/v1",
    ))
    assert "".join(tokens) == "Hello"


def test_call_llm_openai_http_error_maps_to_auth(monkeypatch):
    _route_httpx(monkeypatch, lambda request: httpx.Response(401, json={"error": "bad key"}))
    with pytest.raises(httpx.HTTPStatusError) as info:
        call_llm("openai:m", [{"role": "user", "content": "hi"}], "bad",
                 base_url="https://api.example.com/v1")
    assert friendly_llm_error(info.value)[0] == "auth"


def test_missing_base_url_maps_to_config_error():
    with pytest.raises(ValueError) as info:
        call_llm("openai:m", [{"role": "user", "content": "hi"}], "k")
    assert friendly_llm_error(info.value)[0] == "config"
