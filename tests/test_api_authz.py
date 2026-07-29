"""
Authorization regression tests.

These encode the exact exploits the production audit reproduced with curl:
an unauthenticated caller could read AND destroy any user's knowledge base by
naming them in the request. Each test below fails loudly if that ever returns.
"""

from __future__ import annotations

import pytest

from tests.conftest import auth_header, register_and_login

# Every data route. Adding a new one without auth should break this list.
PROTECTED_ROUTES: list[tuple[str, str, dict | None]] = [
    ("GET", "/api/documents", None),
    ("GET", "/api/documents/stats", None),
    ("POST", "/api/documents/clear", {}),
    ("POST", "/api/documents/summarize", {"title": "x", "api_key": "k"}),
    ("DELETE", "/api/documents", {"title": "x"}),
    ("POST", "/api/semantic-search", {"query": "x"}),
    ("POST", "/api/chat/stream", {"query": "x", "api_key": "k"}),
    ("POST", "/api/openalex/search", {"query": "x", "max_results": 1}),
    ("POST", "/api/openalex/ingest", {"works": [], "mode": "abstracts"}),
    ("GET", "/api/auth/me", None),
]


@pytest.mark.parametrize("method,path,body", PROTECTED_ROUTES)
def test_route_requires_authentication(client, method, path, body):
    """AUDIT C1: every data route must reject an anonymous caller with 401."""
    res = client.request(method, path, json=body)
    assert res.status_code == 401, f"{method} {path} returned {res.status_code}, expected 401"


@pytest.mark.parametrize("method,path,body", PROTECTED_ROUTES)
def test_route_rejects_garbage_token(client, method, path, body):
    res = client.request(
        method, path, json=body, headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert res.status_code == 401


def test_public_routes_stay_public(client):
    """Health/readiness/config must not require a token (probes and boot-up)."""
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/config").status_code == 200


def test_cannot_reach_another_users_data_via_body(client, pdf_upload):
    """
    AUDIT C1 (IDOR): the classic attack was passing someone else's user_id.

    Alice uploads a document. Bob authenticates and asks for documents while
    trying every spelling of "give me alice's data" in the payload. He must only
    ever see his own (empty) library.
    """
    alice = register_and_login(client, "alice")
    res = client.post("/api/documents/upload", headers=auth_header(alice), files=pdf_upload())
    assert res.status_code == 200
    assert res.json()["chunks_added"] > 0

    alice_docs = client.get("/api/documents", headers=auth_header(alice)).json()["documents"]
    assert len(alice_docs) == 1

    bob = register_and_login(client, "bob")

    # Legitimate view: Bob's own library is empty.
    bob_docs = client.get("/api/documents", headers=auth_header(bob)).json()["documents"]
    assert bob_docs == []

    # Spoofing attempts — the field no longer exists in the schema, so these are
    # simply ignored rather than honoured.
    spoofed = client.post(
        "/api/semantic-search",
        headers=auth_header(bob),
        json={"query": "regression", "user_id": "alice", "top_k": 5, "min_score": 0.0},
    )
    assert spoofed.status_code == 200
    assert spoofed.json()["results"] == [], "Bob retrieved Alice's chunks — IDOR regression!"

    stats = client.get("/api/documents/stats?user_id=alice", headers=auth_header(bob)).json()
    assert stats["total_chunks"] == 0, "Query-string user_id was honoured — IDOR regression!"


def test_cannot_destroy_another_users_library(client, pdf_upload):
    """AUDIT C1: `clear` and `delete` used to accept a victim's user_id."""
    alice = register_and_login(client, "alice")
    client.post("/api/documents/upload", headers=auth_header(alice), files=pdf_upload())
    before = client.get("/api/documents/stats", headers=auth_header(alice)).json()["total_chunks"]
    assert before > 0

    bob = register_and_login(client, "bob")
    assert client.post(
        "/api/documents/clear", headers=auth_header(bob), json={"user_id": "alice"}
    ).status_code == 200
    client.request(
        "DELETE", "/api/documents", headers=auth_header(bob), json={"title": "test", "user_id": "alice"}
    )

    after = client.get("/api/documents/stats", headers=auth_header(alice)).json()["total_chunks"]
    assert after == before, "Bob destroyed Alice's library — IDOR regression!"


def test_error_envelope_shape(client):
    """Errors follow the project's documented contract and carry a request id."""
    body = client.get("/api/documents").json()
    assert set(body) >= {"request_id", "error", "message", "status_code"}
    assert body["error"] == "UNAUTHORIZED"
    assert body["status_code"] == 401
    assert body["request_id"]
