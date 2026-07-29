"""
RAG data- and citation-integrity regression tests.

These encode three defects the RAG audit reproduced, all of which caused the
system to tell users something untrue while looking confident:

  R1  a corrected PDF was silently discarded as a duplicate, so the knowledge
      base kept citing the superseded figure forever
  R2  every citation displayed "relevance: 1.00" because parent chunks were
      hardcoded to that score
  R4  the reference list was built before context truncation, so the model
      could be handed a citation label whose passage had been removed
"""

from __future__ import annotations

import re

import pytest

from app.rag import (
    _truncate_context_tracked,
    build_context,
    format_references_for_prompt,
)


# ─── R1: content-addressed chunk ids ─────────────────────────────────────────

def _pdf(text: str) -> bytes:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), text, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


V1 = "VERSION ONE. The measured accuracy of the Zephyr model was 61.4 percent. " * 12
V2 = "VERSION TWO. The corrected accuracy of the Zephyr model was 92.8 percent. " * 12


def test_document_fingerprint_tracks_content_not_filename():
    from app.chunker import document_fingerprint

    assert document_fingerprint(_pdf(V1)) != document_fingerprint(_pdf(V2))
    # Deterministic: same bytes → same fingerprint.
    same = _pdf(V1)
    assert document_fingerprint(same) == document_fingerprint(same)


def test_chunk_ids_change_when_content_changes():
    """The root cause: ids used to hash filename+index only."""
    from app.chunker import extract_pdf_chunks_advanced

    c1, _, _ = extract_pdf_chunks_advanced(_pdf(V1), "paper.pdf")
    c2, _, _ = extract_pdf_chunks_advanced(_pdf(V2), "paper.pdf")

    assert {c.chunk_id for c in c1}.isdisjoint({c.chunk_id for c in c2}), (
        "same filename produced identical chunk ids for different content — "
        "the corrected revision would be discarded as a duplicate"
    )


@pytest.mark.usefixtures("temp_vector_store")
def test_reuploading_corrected_pdf_replaces_stale_revision():
    """AUDIT R1: end to end — the KB must serve the corrected figure."""
    from app.pdf_service import ingest_pdf
    from app.semantic_search import semantic_search

    user = "r1user"

    first = ingest_pdf(_pdf(V1), "paper.pdf", user_id=user)
    assert first["chunks_added"] > 0
    assert first["replaced_revision"] is False

    hits = semantic_search("Zephyr model accuracy", user_id=user, top_k=5)
    assert any("61.4" in h["text"] for h in hits)

    second = ingest_pdf(_pdf(V2), "paper.pdf", user_id=user)
    assert second["chunks_added"] > 0, "corrected revision was silently skipped"
    assert second["replaced_revision"] is True

    hits = semantic_search("Zephyr model accuracy", user_id=user, top_k=10)
    texts = " ".join(h["text"] for h in hits)
    assert "92.8" in texts, "knowledge base did not pick up the correction"
    assert "VERSION ONE" not in texts, "stale revision still present — both would be citable"


@pytest.mark.usefixtures("temp_vector_store")
def test_identical_reupload_is_still_deduplicated():
    """The fix must not turn every re-upload into a duplicate ingest."""
    from app.pdf_service import ingest_pdf

    user = "r1dedup"
    pdf = _pdf(V1)
    ingest_pdf(pdf, "paper.pdf", user_id=user)
    again = ingest_pdf(pdf, "paper.pdf", user_id=user)

    assert again["chunks_added"] == 0
    assert again["replaced_revision"] is False


# ─── R2: honest relevance scores ─────────────────────────────────────────────

def test_reference_scores_are_not_hardcoded_to_one():
    """
    AUDIT R2: build_context must surface the real per-chunk score.

    A weak match and a strong match have to be distinguishable in the UI.
    """
    chunks = ["strong passage", "weak passage"]
    metas = [
        {"title": "Strong", "authors": "A", "published": "2020", "source": "upload", "_score": 0.93},
        {"title": "Weak", "authors": "B", "published": "2019", "source": "upload", "_score": 0.11},
    ]
    _, refs = build_context(chunks, metas)

    scores = [r.relevance_score for r in refs]
    assert scores == [0.93, 0.11]
    assert len(set(scores)) > 1, "all citations report the same score — R2 regression"


# ─── R4: reference list can never outlive its context ────────────────────────

def _numbers_in(text: str) -> set[int]:
    return {int(n) for n in re.findall(r"\[(\d+)\]", text)}


def test_truncation_drops_references_whose_passage_was_removed():
    """AUDIT R4: no citable label may lack a passage."""
    chunks = ["A" * 400, "B" * 400, "C" * 400]
    metas = [
        {"title": f"Paper {n}", "authors": "X", "published": "2020", "source": "upload", "_score": s}
        for n, s in (("Alpha", 0.9), ("Beta", 0.6), ("Gamma", 0.3))
    ]
    context, refs = build_context(chunks, metas)
    assert len(refs) == 3

    trimmed, kept = _truncate_context_tracked(context, max_tokens=200, chars_per_token=4)
    assert kept, "truncation removed everything"
    assert len(kept) < 3, "budget was too generous to exercise truncation"

    numbered = [(n, r) for n, r in enumerate(refs, 1) if n in kept]
    refs_text = format_references_for_prompt(
        [r for _, r in numbered], numbers=[n for n, _ in numbered]
    )

    orphaned = _numbers_in(refs_text) - _numbers_in(trimmed)
    assert not orphaned, f"citations {orphaned} offered with no supporting passage"


def test_truncation_removes_stranded_metadata_headers():
    """A surviving '--- Paper [N]' header with no passage is still an invitation."""
    chunks = ["A" * 400, "B" * 400, "C" * 400]
    metas = [
        {"title": f"P{n}", "authors": "X", "published": "2020", "source": "upload", "_score": 0.5}
        for n in range(3)
    ]
    context, _ = build_context(chunks, metas)
    trimmed, kept = _truncate_context_tracked(context, max_tokens=200, chars_per_token=4)

    for header_num in re.findall(r"--- Paper \[(\d+)\]", trimmed):
        assert int(header_num) in kept, f"header [{header_num}] left without a passage"


def test_untruncated_context_keeps_every_reference():
    """The guard must not drop references when nothing needed trimming."""
    chunks = ["short one", "short two"]
    metas = [
        {"title": "One", "authors": "A", "published": "2020", "source": "upload", "_score": 0.8},
        {"title": "Two", "authors": "B", "published": "2021", "source": "upload", "_score": 0.7},
    ]
    context, refs = build_context(chunks, metas)
    trimmed, kept = _truncate_context_tracked(context, max_tokens=8000)

    assert kept == {1, 2}
    assert "truncated to fit token limit" not in trimmed
    assert len(refs) == 2


def test_format_references_preserves_original_numbering():
    """Filtered references must keep their context numbers, not be renumbered."""
    from app.rag import Reference

    refs = [
        Reference("Alpha", "A", "2020", "", "upload", 0.9),
        Reference("Gamma", "C", "2019", "", "upload", 0.3),
    ]
    text = format_references_for_prompt(refs, numbers=[1, 3])
    assert text.startswith("[1] Alpha")
    assert "[3] Gamma" in text
    assert "[2]" not in text
