"""
API tests for /api/suggestions.

These use a TestClient WITHOUT entering its context manager, so the app's
lifespan (which loads the embedding and reranker models) never runs. The
suggestion functions are stubbed, so no model, vector store or network is
needed.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import api.routers.suggestions as suggestions_router
from tests.conftest import auth_header, register_and_login


@pytest.fixture
def light_client(temp_auth_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Auth-capable client that skips model loading; rate limiting disabled."""
    monkeypatch.setenv("JWT_SECRET", "test-secret-" + "x" * 40)
    monkeypatch.setenv("ENVIRONMENT", "development")

    import api.main as api_main
    from api.settings import get_api_settings

    get_api_settings.cache_clear()
    api_main.app.state.limiter.enabled = False
    yield TestClient(api_main.app, raise_server_exceptions=False)
    api_main.app.state.limiter.enabled = True
    get_api_settings.cache_clear()


def test_kb_suggestions_valid_request_returns_200(light_client, monkeypatch):
    seen = {}

    def fake_suggest(user_id, **kwargs):
        seen.update(kwargs, user_id=user_id)
        return ["How does LoRA reduce trainable parameters?"]

    monkeypatch.setattr(suggestions_router, "suggest_questions_from_kb", fake_suggest)
    tokens = register_and_login(light_client)

    res = light_client.post(
        "/api/suggestions",
        json={
            "model": "openai:llama3.1",
            "base_url": "http://localhost:11434/v1",
            "language": "id",
            "exclude": ["Old question?"],
        },
        headers=auth_header(tokens),
    )

    assert res.status_code == 200, res.text
    assert res.json() == {"suggestions": ["How does LoRA reduce trainable parameters?"]}
    assert seen["user_id"] == tokens["user_id"]
    assert seen["api_key"] is None  # empty key is passed on as "no key"
    assert seen["base_url"] == "http://localhost:11434/v1"
    assert seen["language"] == "id"
    assert seen["exclude"] == ["Old question?"]


def test_kb_suggestions_llm_failure_returns_502_envelope(light_client, monkeypatch):
    def boom(user_id, **kwargs):
        raise RuntimeError("Error code: 429 - rate limit reached")

    monkeypatch.setattr(suggestions_router, "suggest_questions_from_kb", boom)
    tokens = register_and_login(light_client)

    res = light_client.post(
        "/api/suggestions", json={"api_key": "k"}, headers=auth_header(tokens),
    )

    assert res.status_code == 502
    body = res.json()
    assert body["error"] == "UPSTREAM_ERROR"
    assert "rate limit" in body["message"].lower()
    assert "429" not in body["message"]  # friendly headline, not the raw provider text


def test_kb_suggestions_invalid_base_url_returns_422(light_client):
    tokens = register_and_login(light_client)
    res = light_client.post(
        "/api/suggestions",
        json={"base_url": "file:///etc/passwd"},
        headers=auth_header(tokens),
    )
    assert res.status_code == 422


def test_kb_suggestions_requires_auth(light_client):
    assert light_client.post("/api/suggestions", json={}).status_code == 401


def test_followups_valid_request_returns_200(light_client, monkeypatch):
    seen = {}

    def fake_followups(question, answer, **kwargs):
        seen.update(kwargs, question=question, answer=answer)
        return ["How does LoRA compare to adapters?"]

    monkeypatch.setattr(suggestions_router, "generate_followup_questions", fake_followups)
    tokens = register_and_login(light_client)

    res = light_client.post(
        "/api/suggestions/followups",
        json={"question": "What is LoRA?", "answer": "LoRA freezes weights [1].",
              "api_key": "k", "model": "gemini-3.5-flash"},
        headers=auth_header(tokens),
    )

    assert res.status_code == 200, res.text
    assert res.json()["suggestions"] == ["How does LoRA compare to adapters?"]
    assert seen["question"] == "What is LoRA?"
    assert seen["n"] == 3
