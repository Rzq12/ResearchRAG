"""
fulltext_service.py
-------------------
Fetch full-text open-access PDFs for OpenAlex works.

Strategy (in order):
1. Semantic Scholar Graph API  – free, no auth needed for basic queries
2. Unpaywall API               – free, requires an email address
3. Direct URL from OpenAlex    – sometimes the landing_page_url is itself a PDF

Returns the PDF bytes so the caller can pass them to `ingest_pdf`.
"""

from __future__ import annotations

import ipaddress
import socket

import httpx
from dataclasses import dataclass
from app.config import get_settings


@dataclass
class FulltextResult:
    pdf_url: str
    source: str          # "semantic_scholar" | "unpaywall" | "direct"
    pdf_bytes: bytes


# ─── DOI helpers ─────────────────────────────────────────────────────────────

def _extract_doi(url: str) -> str | None:
    """Extract a bare DOI (e.g. '10.1145/…') from various URL forms."""
    if not url:
        return None
    for prefix in ("https://doi.org/", "http://doi.org/"):
        if url.startswith(prefix):
            return url[len(prefix):]
    if "doi.org/" in url:
        return url.split("doi.org/", 1)[-1]
    if url.startswith("10."):
        return url
    return None


# ─── Source-specific fetchers ─────────────────────────────────────────────────

def _semantic_scholar_pdf_url(doi: str) -> str | None:
    """
    Query Semantic Scholar Graph API for an open-access PDF URL.
    Docs: https://api.semanticscholar.org/graph/v1
    """
    try:
        with httpx.Client(timeout=15, headers={"User-Agent": "arxiv-rag/1.0"}) as client:
            resp = client.get(
                f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}",
                params={"fields": "openAccessPdf,externalIds"},
            )
            if resp.status_code == 200:
                data = resp.json()
                oa = data.get("openAccessPdf")
                if oa and oa.get("url"):
                    return oa["url"]
    except Exception:
        pass
    return None


def _unpaywall_pdf_url(doi: str) -> str | None:
    """
    Query Unpaywall for an open-access PDF URL.
    Docs: https://unpaywall.org/products/api
    Requires an email for the 'polite pool'.
    """
    cfg = get_settings()
    email = cfg.fulltext_mailto or cfg.openalex_mailto or "user@example.com"
    try:
        with httpx.Client(timeout=15, headers={"User-Agent": "arxiv-rag/1.0"}) as client:
            resp = client.get(
                f"https://api.unpaywall.org/v2/{doi}",
                params={"email": email},
            )
            if resp.status_code == 200:
                data = resp.json()
                best = data.get("best_oa_location") or {}
                # prefer a direct PDF link; fall back to landing page
                return best.get("url_for_pdf") or best.get("url")
    except Exception:
        pass
    return None


_MAX_REDIRECTS = 3


def _assert_public_http_url(url: httpx.URL) -> None:
    """
    Reject anything that is not a public http(s) endpoint.

    These URLs are attacker-steerable: a DOI resolves to whatever its owner
    registered, and Unpaywall echoes third-party ``best_oa_location.url``. With
    redirects followed blindly this was a *readable* SSRF — the response body is
    ingested into the caller's knowledge base and can then be read straight back
    out through /ask, so a redirect to a cloud metadata endpoint exfiltrated
    instance credentials.
    """
    if url.scheme not in ("http", "https"):
        raise ValueError(f"blocked scheme: {url.scheme!r}")
    host = url.host
    if not host:
        raise ValueError("missing host")
    # Resolve and check EVERY address the name maps to, so a name with one
    # public and one private A record cannot slip through.
    try:
        infos = socket.getaddrinfo(host, url.port or (443 if url.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise ValueError(f"unresolvable host: {host}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local      # 169.254.0.0/16 — cloud metadata
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise ValueError(f"blocked non-public address {ip} for host {host}")


def _download_pdf(url: str) -> bytes | None:
    """Download a PDF from a URL. Returns bytes or None on failure."""
    cfg = get_settings()
    max_bytes = cfg.fulltext_max_pdf_mb * 1024 * 1024
    try:
        # follow_redirects=False + a bounded manual loop: every hop is
        # re-validated, which blind redirect-following could not do.
        with httpx.Client(
            timeout=60,
            follow_redirects=False,
            headers={"User-Agent": "arxiv-rag/1.0"},
        ) as client:
            current = httpx.URL(url)
            for _ in range(_MAX_REDIRECTS + 1):
                _assert_public_http_url(current)
                with client.stream("GET", current) as resp:
                    if resp.is_redirect:
                        location = resp.headers.get("location")
                        if not location:
                            return None
                        current = current.join(location)
                        continue
                    if resp.status_code != 200:
                        return None
                    content_type = resp.headers.get("content-type", "").lower()
                    # Allowlist rather than the old "reject html" denylist: a
                    # metadata endpoint returns JSON or text/plain and sailed
                    # straight through.
                    if not any(
                        t in content_type
                        for t in ("application/pdf", "application/x-pdf", "octet-stream")
                    ):
                        return None
                    chunks = []
                    total = 0
                    for chunk in resp.iter_bytes(chunk_size=65536):
                        total += len(chunk)
                        if total > max_bytes:
                            return None  # too large, abort
                        chunks.append(chunk)
                    return b"".join(chunks)
            return None  # redirect budget exhausted
    except Exception:
        return None


# ─── Public API ───────────────────────────────────────────────────────────────

def fetch_fulltext(work_url: str) -> FulltextResult | None:
    """
    Try to find and download an open-access full-text PDF for a paper.

    Parameters
    ----------
    work_url : str
        The URL/DOI string from an OpenAlexWork (work.url).

    Returns
    -------
    FulltextResult on success, None if no open-access PDF could be found/downloaded.
    """
    doi = _extract_doi(work_url)
    if not doi:
        return None

    candidates: list[tuple[str, str]] = []  # (pdf_url, source_label)

    # 1. Semantic Scholar
    s2_url = _semantic_scholar_pdf_url(doi)
    if s2_url:
        candidates.append((s2_url, "semantic_scholar"))

    # 2. Unpaywall
    uw_url = _unpaywall_pdf_url(doi)
    if uw_url and uw_url != s2_url:
        candidates.append((uw_url, "unpaywall"))

    # 3. Direct DOI URL (sometimes resolves to a PDF)
    doi_url = f"https://doi.org/{doi}"
    if doi_url not in {u for u, _ in candidates}:
        candidates.append((doi_url, "direct"))

    for pdf_url, source in candidates:
        pdf_bytes = _download_pdf(pdf_url)
        if pdf_bytes and len(pdf_bytes) > 1024:  # sanity: at least 1 KB
            return FulltextResult(pdf_url=pdf_url, source=source, pdf_bytes=pdf_bytes)

    return None


def fetch_fulltext_batch(
    works: list,  # list[OpenAlexWork]
    user_id: str | None = None,
    status_callback=None,
) -> dict:
    """
    Fetch and ingest full-text PDFs for a list of OpenAlexWork objects.

    Parameters
    ----------
    works : list[OpenAlexWork]
    user_id : str | None
    status_callback : callable(msg: str) | None
        Called with a status string for each work processed.

    Returns
    -------
    dict with keys: fetched, skipped, failed, details (list of dicts)
    """
    from app.pdf_service import ingest_pdf  # local import to avoid circular

    results = {"fetched": 0, "skipped": 0, "failed": 0, "details": []}

    for work in works:
        if status_callback:
            status_callback(f"🔍 Looking for full-text: {work.title[:60]}…")

        result = fetch_fulltext(work.url)
        if result is None:
            results["failed"] += 1
            results["details"].append({
                "title": work.title,
                "status": "no_oa_pdf",
                "source": None,
            })
            continue

        # Use filename = "fulltext_{sanitized_title}.pdf" for the doc key
        safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in work.title)
        filename = f"fulltext_{safe_title[:80]}.pdf"

        if status_callback:
            status_callback(f"📥 Ingesting full-text ({result.source}): {work.title[:50]}…")

        try:
            ingest_result = ingest_pdf(result.pdf_bytes, filename, user_id=user_id)
            if ingest_result["chunks_added"] > 0:
                results["fetched"] += 1
                results["details"].append({
                    "title": work.title,
                    "status": "ingested",
                    "source": result.source,
                    "chunks": ingest_result["chunks_added"],
                    "pdf_url": result.pdf_url,
                })
            else:
                results["skipped"] += 1
                results["details"].append({
                    "title": work.title,
                    "status": "already_indexed",
                    "source": result.source,
                })
        except ValueError as e:
            results["failed"] += 1
            results["details"].append({
                "title": work.title,
                "status": f"ingest_error: {e}",
                "source": result.source,
            })

    return results
