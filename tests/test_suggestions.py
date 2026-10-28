"""Unit tests for question suggestions: parsing, KB grounding, follow-ups."""

import pytest
from pydantic import ValidationError

import app.rag as rag
from api.schemas import KbSuggestionsRequest
from app.config import get_settings


class FakeCollection:
    """Minimal stand-in for a Chroma collection: rows in insertion order."""

    def __init__(self, rows: list[tuple[str, dict]]):
        self.rows = rows

    def get(self, where=None, include=None):
        rows = [
            (text, meta) for text, meta in self.rows
            if not where or meta.get("title") == where["title"]
        ]
        return {"documents": [t for t, _ in rows], "metadatas": [m for _, m in rows]}


def _chunk(title: str, idx: int, text: str, section: str = "") -> tuple[str, dict]:
    return text, {"title": title, "chunk_index": idx, "section_title": section}


@pytest.fixture
def captured_llm(monkeypatch):
    """Record call_llm kwargs and return a canned JSON reply."""
    calls: list[dict] = []
    reply = {"text": '{"questions": ["How does LoRA reduce trainable parameters?"]}'}

    def fake_call_llm(**kwargs):
        calls.append(kwargs)
        return reply["text"]

    monkeypatch.setattr(rag, "call_llm", fake_call_llm)
    return calls, reply


# ─── parse_question_list ──────────────────────────────────────────────────────

def test_parse_question_list_json_object_returns_questions():
    raw = '{"questions": ["What dataset was used for evaluation?", "Why does LoRA work?"]}'
    assert rag.parse_question_list(raw, 5) == [
        "What dataset was used for evaluation?", "Why does LoRA work?",
    ]


def test_parse_question_list_fenced_json_after_think_block():
    raw = (
        "<think>the user wants questions</think>\n"
        '```json\n["Which baseline does the paper compare against?"]\n```'
    )
    assert rag.parse_question_list(raw, 5) == ["Which baseline does the paper compare against?"]


def test_parse_question_list_numbered_fallback_skips_preamble():
    raw = (
        "Here are some research questions for you:\n"
        "1. **What is the main contribution of the paper?**\n"
        "2) How is the model evaluated on GLUE?\n"
        "- What are the stated limitations?\n"
    )
    assert rag.parse_question_list(raw, 5) == [
        "What is the main contribution of the paper?",
        "How is the model evaluated on GLUE?",
        "What are the stated limitations?",
    ]


def test_parse_question_list_dedupes_and_respects_exclude_and_n():
    raw = (
        '{"questions": ["What is RAG?? no", "Too short?", '
        '"How is retrieval evaluated?", "how is retrieval evaluated?", '
        '"Which encoder is used here?", "What does HyDE add to retrieval?"]}'
    )
    out = rag.parse_question_list(raw, 2, exclude=["Which encoder is used here?"])
    assert out == ["What is RAG?? no", "How is retrieval evaluated?"]


def test_parse_question_list_garbage_returns_empty():
    assert rag.parse_question_list("I cannot help with that.", 5) == []
    assert rag.parse_question_list("", 5) == []


# ─── suggest_questions_from_kb ────────────────────────────────────────────────

def test_suggest_from_kb_prompt_uses_chunk_text_not_just_title(monkeypatch, captured_llm):
    calls, _ = captured_llm
    collection = FakeCollection([
        _chunk("lora_paper", 1, "We freeze the pretrained weights and inject rank "
               "decomposition matrices.", "Method"),
        _chunk("lora_paper", 0, "LoRA: Low-Rank Adaptation of large language models.",
               "Abstract"),
    ])
    monkeypatch.setattr(rag, "get_collection", lambda user_id: collection)

    out = rag.suggest_questions_from_kb(
        "u1", api_key="k", model="llama-3.1-8b-instant", language="id",
    )

    assert out == ["How does LoRA reduce trainable parameters?"]
    prompt = calls[0]["messages"][1]["content"]
    assert "rank decomposition matrices" in prompt
    # Chunks are ordered by chunk_index, so the abstract comes first.
    assert prompt.index("Low-Rank Adaptation") < prompt.index("rank decomposition")
    assert "Sections: Abstract; Method" in prompt
    assert "Indonesian" in prompt


def test_suggest_from_kb_defaults_to_most_recent_documents(monkeypatch, captured_llm):
    calls, _ = captured_llm
    rows = [_chunk(f"paper_{i}", 0, f"Text of paper {i}.") for i in range(8)]
    monkeypatch.setattr(rag, "get_collection", lambda user_id: FakeCollection(rows))

    rag.suggest_questions_from_kb("u1", api_key="k", model="llama-3.1-8b-instant")

    prompt = calls[0]["messages"][1]["content"]
    assert "paper_7" in prompt and "paper_2" in prompt
    assert "paper_1" not in prompt and "paper_0" not in prompt


def test_suggest_from_kb_empty_kb_skips_llm(monkeypatch, captured_llm):
    calls, _ = captured_llm
    monkeypatch.setattr(rag, "get_collection", lambda user_id: FakeCollection([]))
    assert rag.suggest_questions_from_kb("u1", api_key="k", model="m") == []
    assert calls == []


def test_suggest_from_kb_custom_endpoint_gets_no_server_key(monkeypatch, captured_llm):
    calls, _ = captured_llm
    monkeypatch.setattr(get_settings(), "groq_api_key", "server-secret")
    monkeypatch.setattr(
        rag, "get_collection", lambda user_id: FakeCollection([_chunk("p", 0, "Body.")]),
    )

    rag.suggest_questions_from_kb(
        "u1", api_key=None, model="openai:llama3.1", base_url="http://localhost:11434/v1",
    )

    assert calls[0]["api_key"] is None
    assert calls[0]["base_url"] == "http://localhost:11434/v1"


def test_suggest_from_kb_missing_required_key_raises(monkeypatch, captured_llm):
    monkeypatch.setattr(get_settings(), "groq_api_key", None)
    monkeypatch.setattr(
        rag, "get_collection", lambda user_id: FakeCollection([_chunk("p", 0, "Body.")]),
    )
    with pytest.raises(ValueError, match="API key required"):
        rag.suggest_questions_from_kb("u1", api_key=None, model="llama-3.1-8b-instant")


def test_suggest_from_kb_passes_exclude_to_prompt(monkeypatch, captured_llm):
    calls, reply = captured_llm
    reply["text"] = '{"questions": ["Old question about LoRA?", "A brand new question here?"]}'
    monkeypatch.setattr(
        rag, "get_collection", lambda user_id: FakeCollection([_chunk("p", 0, "Body.")]),
    )

    out = rag.suggest_questions_from_kb(
        "u1", api_key="k", model="m", exclude=["Old question about LoRA?"],
    )

    assert out == ["A brand new question here?"]
    assert "Old question about LoRA?" in calls[0]["messages"][1]["content"]


# ─── follow-ups & legacy entry point ──────────────────────────────────────────

def test_followups_never_repeat_original_question(captured_llm):
    calls, reply = captured_llm
    reply["text"] = (
        '{"questions": ["What is LoRA exactly?", "How does LoRA compare to adapters?"]}'
    )
    out = rag.generate_followup_questions(
        "What is LoRA exactly?", "LoRA freezes weights [1].", api_key="k", model="m",
    )
    assert out == ["How does LoRA compare to adapters?"]
    assert "LoRA freezes weights" in calls[0]["messages"][1]["content"]


def test_followups_empty_answer_skips_llm(captured_llm):
    calls, _ = captured_llm
    assert rag.generate_followup_questions("q?", "   ", api_key="k", model="m") == []
    assert calls == []


def test_legacy_generate_query_suggestions_fails_soft(monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("429 rate limit")

    monkeypatch.setattr(rag, "call_llm", boom)
    assert rag.generate_query_suggestions(["Some title"], api_key="k", model="m") == []


# ─── request schema ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("url", ["http://localhost:11434/v1", "https://openrouter.ai/api/v1"])
def test_kb_suggestions_request_accepts_http_urls(url):
    assert KbSuggestionsRequest(base_url=url).base_url == url


@pytest.mark.parametrize("url", ["ftp://example.com", "localhost:11434", "https://"])
def test_kb_suggestions_request_rejects_non_http_urls(url):
    with pytest.raises(ValidationError):
        KbSuggestionsRequest(base_url=url)


def test_kb_suggestions_request_blank_url_becomes_none():
    assert KbSuggestionsRequest(base_url="  ").base_url is None
