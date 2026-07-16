"""
Integration tests for the full RAG pipeline (Fase 5/6/7 plumbing).

Real components: e5 embeddings, ChromaDB, BM25, cross-encoder reranker.
Mocked: every LLM call and live network fallback — tests run offline.

Slow-ish (loads models once); run with the project venv:
    .venv/Scripts/python -m pytest tests/test_integration_pipeline.py -q
"""

import json
from pathlib import Path

import pytest

import app.hyde as hyde_mod
import app.fallback as fb_mod
import app.rag as rag_mod
from eval.run_eval import _reset_eval_collections, ingest_corpus, EVAL_USER


@pytest.fixture(scope="module")
def eval_kb():
    corpus = json.loads(
        (Path(__file__).parent.parent / "eval" / "corpus.json").read_text(encoding="utf-8")
    )
    _reset_eval_collections()
    ingest_corpus(corpus)
    yield
    _reset_eval_collections()


# ─── Fase 5: HyDE plumbing ────────────────────────────────────────────────────

def test_hyde_hypotheticals_used_as_extra_queries(eval_kb, monkeypatch):
    calls = []

    def fake_llm(model, messages, api_key, max_tokens, temperature):
        calls.append(messages[-1]["content"])
        return "Low-rank adapters freeze pretrained weights and train small matrices."

    monkeypatch.setattr(hyde_mod, "call_llm", fake_llm)

    chunks, metas = rag_mod.retrieve_chunks(
        "How does LoRA reduce fine-tuning cost?",
        user_id=EVAL_USER, api_key="fake-key", model="fake-model",
    )
    assert len(calls) == 2          # n=2 hypothetical docs generated
    assert chunks                   # retrieval still works
    # lora/qlora both discuss low-rank adapters — either may rank first
    top2 = {m.get("eval_doc_id") for m in metas[:2]}
    assert "lora" in top2


def test_hyde_skipped_without_api_key(eval_kb, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("HyDE must not run without api_key")

    monkeypatch.setattr(hyde_mod, "generate_hypotheticals", boom)
    chunks, _ = rag_mod.retrieve_chunks("What is BERT?", user_id=EVAL_USER)
    assert chunks


# ─── Fase 6: relevance threshold + fallback ───────────────────────────────────

def test_relevant_query_stays_on_kb(eval_kb):
    cfg = rag_mod.get_settings()
    prepared = rag_mod._prepare_context(
        "What is double quantization in QLoRA?", cfg, EVAL_USER, None, None, None,
    )
    assert prepared is not None
    context, refs, source = prepared
    assert source == "kb"
    assert "QLoRA" in context


def test_offtopic_query_triggers_fallback(eval_kb, monkeypatch):
    monkeypatch.setattr(
        fb_mod, "fallback_context",
        lambda q: ("live context", [{"title": "T", "source": "openalex-live"}], "openalex-live"),
    )
    cfg = rag_mod.get_settings()
    prepared = rag_mod._prepare_context(
        "Resep rendang daging sapi yang empuk dan bumbunya meresap",
        cfg, EVAL_USER, None, None, None,
    )
    context, refs, source = prepared
    assert source == "openalex-live"
    assert context == "live context"
    assert refs[0].source == "openalex-live"


def test_offtopic_query_all_sources_fail_returns_none_source(eval_kb, monkeypatch):
    monkeypatch.setattr(fb_mod, "fallback_context", lambda q: ("", [], "none"))
    cfg = rag_mod.get_settings()
    prepared = rag_mod._prepare_context(
        "Cara memasang genteng rumah yang bocor saat musim hujan",
        cfg, EVAL_USER, None, None, None,
    )
    context, refs, source = prepared
    assert source == "none"
    assert refs == []


# ─── Fase 7: <think> reasoning through ask()/ask_stream() ─────────────────────

def test_ask_parses_think_block(eval_kb, monkeypatch):
    monkeypatch.setattr(
        rag_mod, "call_llm",
        lambda **kw: "<think>papers [1] relevant</think>\n\nLoRA freezes weights [1].",
    )
    monkeypatch.setattr(hyde_mod, "call_llm", lambda **kw: "hypothetical")

    response = rag_mod.ask(
        "How does LoRA work?", api_key="fake", model="fake-model", user_id=EVAL_USER,
    )
    assert response.reasoning == "papers [1] relevant"
    assert response.answer == "LoRA freezes weights [1]."
    assert "<think>" not in response.answer
    assert response.source == "kb"
    assert response.references


def test_ask_stream_splits_think(eval_kb, monkeypatch):
    def fake_stream(**kw):
        yield from ["<think>", "checking [1]", "</think>", "\n\n", "Answer ", "[1]."]

    monkeypatch.setattr(rag_mod, "stream_llm", fake_stream)
    monkeypatch.setattr(hyde_mod, "call_llm", lambda **kw: "hypothetical")

    gen, refs, oa, up, think, source = rag_mod.ask_stream(
        "What is BERT pre-training?", api_key="fake", model="fake-model", user_id=EVAL_USER,
    )
    answer = "".join(gen)
    assert answer == "Answer [1]."
    assert think["think"] == "checking [1]"
    assert source == "kb"
    assert refs
