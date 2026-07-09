from __future__ import annotations

import json
from types import SimpleNamespace

import httpx

from opensquilla.knowledge.backend import DisabledKnowledgeBackend
from opensquilla.knowledge.http_backend import HttpKnowledgeBackend
from opensquilla.knowledge.manager import manager_from_config


def test_http_knowledge_backend_calls_standalone_api() -> None:
    requests: list[tuple[str, str, dict | None, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8")) if request.content else None
        requests.append(
            (
                request.method,
                request.url.path,
                body,
                request.headers.get("authorization"),
            )
        )
        if request.url.path == "/v1/status":
            return httpx.Response(200, json={"ok": True})
        if request.url.path == "/v1/ingest":
            return httpx.Response(200, json={"ok": True, "collectionId": body["collectionId"]})
        if request.url.path == "/v1/search":
            return httpx.Response(200, json={"query": body["query"], "results": [], "count": 0})
        if request.url.path == "/v1/chunks/missing":
            return httpx.Response(404, json={"error": {"code": "not_found"}})
        return httpx.Response(500, json={"error": {"message": "unexpected path"}})

    backend = HttpKnowledgeBackend(
        "http://knowledge.local",
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    )

    assert backend.status()["ok"] is True
    ingest = backend.ingest_collection(source_root="/tmp/source", collection_id="research")
    assert ingest["collectionId"] == "research"
    assert (
        backend.search(
            "AI 光模块",
            top_k=3,
            filters={
                "collectionId": "datasets",
                "retrievalProfile": "hybrid_rrf_bge_m3_fts5",
                "embeddingModel": "baai/bge-m3",
                "embeddingDimensions": 1024,
            },
        )["query"]
        == "AI 光模块"
    )
    assert backend.get(chunk_id="missing") is None
    assert requests == [
        ("GET", "/v1/status", None, "Bearer test-key"),
        (
            "POST",
            "/v1/ingest",
            {
                "sourceRoot": "/tmp/source",
                "limit": 60,
                "collectionName": None,
                "collectionId": "research",
                "indexProfiles": None,
            },
            "Bearer test-key",
        ),
        (
            "POST",
            "/v1/search",
            {
                "query": "AI 光模块",
                "topK": 3,
                "filters": {
                    "collectionId": "datasets",
                    "retrievalProfile": "hybrid_rrf_bge_m3_fts5",
                    "embeddingModel": "baai/bge-m3",
                    "embeddingDimensions": 1024,
                },
            },
            "Bearer test-key",
        ),
        ("GET", "/v1/chunks/missing", None, "Bearer test-key"),
    ]


def test_manager_from_config_selects_disabled_backend() -> None:
    config = SimpleNamespace(knowledge=SimpleNamespace(enabled=False))

    assert isinstance(manager_from_config(config), DisabledKnowledgeBackend)
