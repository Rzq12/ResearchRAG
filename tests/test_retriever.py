"""Unit tests for app/retriever.py — tokenization and RRF fusion (pure logic)."""

from app.retriever import _tokenize, rrf_fuse


# ─── Tokenizer ────────────────────────────────────────────────────────────────

def test_tokenize_lowercases_and_splits():
    assert _tokenize("LoRA fine-tuning of GPT-3!") == ["lora", "fine", "tuning", "of", "gpt", "3"]


def test_tokenize_handles_indonesian():
    assert _tokenize("Analisis sentimen Bahasa Indonesia") == [
        "analisis", "sentimen", "bahasa", "indonesia"
    ]


def test_tokenize_empty():
    assert _tokenize("") == []


# ─── RRF fusion ───────────────────────────────────────────────────────────────

def _cand(cid, text="t"):
    return {"id": cid, "text": text, "metadata": {}, "_score": 0.5}


def test_rrf_candidate_in_both_lists_ranks_first():
    vector = [_cand("a"), _cand("b"), _cand("c")]
    bm25   = [_cand("c"), _cand("d")]
    fused  = rrf_fuse(vector, bm25, vector_weight=0.6, bm25_weight=0.4)
    # "c" gets contributions from both lists → beats "a" (vector rank 1 only)
    ids = [c["id"] for c in fused]
    assert ids[0] == "c"
    assert set(ids) == {"a", "b", "c", "d"}


def test_rrf_dedup_keeps_one_entry_per_id():
    fused = rrf_fuse([_cand("x")], [_cand("x")])
    assert len(fused) == 1
    # combined score = 0.6/(60+1) + 0.4/(60+1)
    assert abs(fused[0]["_rrf"] - (1.0 / 61)) < 1e-6


def test_rrf_respects_weights():
    # Same rank in each list — higher weight side must win.
    fused = rrf_fuse([_cand("vec_only")], [_cand("bm_only")],
                     vector_weight=0.6, bm25_weight=0.4)
    assert fused[0]["id"] == "vec_only"
    assert fused[1]["id"] == "bm_only"


def test_rrf_empty_lists():
    assert rrf_fuse([], []) == []
    only_vec = rrf_fuse([_cand("a")], [])
    assert [c["id"] for c in only_vec] == ["a"]


def test_rrf_preserves_candidate_payload():
    vector = [{"id": "a", "text": "hello", "metadata": {"title": "T"}, "_score": 0.9}]
    fused  = rrf_fuse(vector, [])
    assert fused[0]["text"] == "hello"
    assert fused[0]["metadata"] == {"title": "T"}
    assert fused[0]["_score"] == 0.9
