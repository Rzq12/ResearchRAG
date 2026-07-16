"""Unit tests for app/fallback.py ordering and app/hyde.py behavior (mocked LLM/network)."""

import app.fallback as fb
import app.hyde as hyde


# ─── fallback_context ordering ────────────────────────────────────────────────

def test_fallback_prefers_openalex(monkeypatch):
    monkeypatch.setattr(fb, "openalex_fallback",
                        lambda q, n: ("papers ctx", [{"source": "openalex-live"}]))
    monkeypatch.setattr(fb, "duckduckgo_fallback",
                        lambda q, n: ("web ctx", [{"source": "web"}]))
    context, refs, note = fb.fallback_context("q")
    assert context == "papers ctx"
    assert note == "openalex-live"


def test_fallback_uses_web_when_openalex_empty(monkeypatch):
    monkeypatch.setattr(fb, "openalex_fallback", lambda q, n: ("", []))
    monkeypatch.setattr(fb, "duckduckgo_fallback",
                        lambda q, n: ("web ctx", [{"source": "web"}]))
    context, refs, note = fb.fallback_context("q")
    assert context == "web ctx"
    assert note == "web"


def test_fallback_returns_none_note_when_all_empty(monkeypatch):
    monkeypatch.setattr(fb, "openalex_fallback", lambda q, n: ("", []))
    monkeypatch.setattr(fb, "duckduckgo_fallback", lambda q, n: ("", []))
    context, refs, note = fb.fallback_context("q")
    assert context == ""
    assert refs == []
    assert note == "none"


def test_openalex_fallback_survives_api_error(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("network down")
    monkeypatch.setattr("app.openalex_service.search_openalex", boom)
    context, refs = fb.openalex_fallback("q", 3)
    assert context == ""
    assert refs == []


# ─── HyDE ─────────────────────────────────────────────────────────────────────

def test_hyde_generates_n_hypotheticals(monkeypatch):
    calls = []

    def fake_llm(model, messages, api_key, max_tokens, temperature):
        calls.append(messages)
        return "A hypothetical abstract paragraph."

    monkeypatch.setattr(hyde, "call_llm", fake_llm)
    out = hyde.generate_hypotheticals("What is LoRA?", api_key="k", model="m", n=2)
    assert len(out) == 2
    assert len(calls) == 2


def test_hyde_system_prompt_enforces_same_language(monkeypatch):
    captured = {}

    def fake_llm(model, messages, api_key, max_tokens, temperature):
        captured["system"] = messages[0]["content"]
        return "ok"

    monkeypatch.setattr(hyde, "call_llm", fake_llm)
    hyde.generate_hypotheticals("Apa itu LoRA?", api_key="k", model="m", n=1)
    assert "SAME LANGUAGE" in captured["system"]


def test_hyde_fails_soft_on_llm_error(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("rate limited")
    monkeypatch.setattr(hyde, "call_llm", boom)
    out = hyde.generate_hypotheticals("q", api_key="k", model="m", n=2)
    assert out == []


def test_hyde_skips_empty_generations(monkeypatch):
    responses = iter(["", "  ", "real one"])

    def fake_llm(*a, **k):
        return next(responses)

    monkeypatch.setattr(hyde, "call_llm", fake_llm)
    out = hyde.generate_hypotheticals("q", api_key="k", model="m", n=3)
    assert out == ["real one"]
