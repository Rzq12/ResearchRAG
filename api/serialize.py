"""
Serialization helpers.

Convert the backend's dataclasses / plain objects (``OpenAlexWork``,
``Reference``, ``CoverageReport`` …) into JSON-safe dicts for the API responses.
Kept in one place so the routers stay small and the wire format is consistent.
"""

from __future__ import annotations

from typing import Any


def work_to_dict(work: Any) -> dict[str, Any]:
    """Serialize an ``app.openalex_service.OpenAlexWork``."""
    return {
        "openalex_id": getattr(work, "openalex_id", ""),
        "title": getattr(work, "title", ""),
        "authors": list(getattr(work, "authors", []) or []),
        "abstract": getattr(work, "abstract", ""),
        "published": getattr(work, "published", ""),
        "url": getattr(work, "url", ""),
        "referenced_works": list(getattr(work, "referenced_works", []) or []),
        "concepts": list(getattr(work, "concepts", []) or []),
        "citation_count": getattr(work, "citation_count", 0) or 0,
    }


def reference_to_dict(ref: Any) -> dict[str, Any]:
    """Serialize an ``app.rag.Reference``."""
    return {
        "title": getattr(ref, "title", ""),
        "authors": getattr(ref, "authors", ""),
        "published": getattr(ref, "published", ""),
        "url": getattr(ref, "url", ""),
        "source": getattr(ref, "source", ""),
        "relevance_score": round(float(getattr(ref, "relevance_score", 0.0) or 0.0), 4),
    }


def coverage_to_dict(coverage: Any) -> dict[str, Any] | None:
    """Serialize an ``app.chunker.CoverageReport`` (may be ``None``)."""
    if coverage is None:
        return None
    return {
        "coverage_pct": getattr(coverage, "coverage_pct", None),
        "covered_pages": getattr(coverage, "covered_pages", None),
        "total_pages": getattr(coverage, "total_pages", None),
        "fallback_used": getattr(coverage, "fallback_used", None),
        "missing_pages": getattr(coverage, "missing_pages", None),
    }


def ingest_result_to_dict(result: dict[str, Any]) -> dict[str, Any]:
    """Normalize the dict returned by ``ingest_pdf`` for the wire."""
    out = dict(result)
    if "coverage" in out:
        out["coverage"] = coverage_to_dict(out["coverage"])
    return out
