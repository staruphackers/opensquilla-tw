from __future__ import annotations

import json

import pytest

from opensquilla.rag.tools import create_rag_tools
from opensquilla.rag.types import RagRetrievalMode
from opensquilla.tools.registry import ToolRegistry
from opensquilla.tools.types import CallerKind, ToolContext


class FakeRagManager:
    def __init__(self) -> None:
        self.search_requests = []

    async def search(self, request):
        self.search_requests.append(request)
        return {
            "query": request.query,
            "mode": request.mode.value if request.mode else None,
            "results": [
                {
                    "content": "local document content",
                    "citation": {"label": "[来源：guide.md]"},
                    "sourceKind": "rag",
                    "untrustedEvidence": True,
                }
            ],
        }

    async def show(self, **_kwargs):
        return {
            "content": "local document content",
            "citation": {"label": "[来源：guide.md]"},
            "sourceKind": "rag",
            "untrustedEvidence": True,
        }


class LargeRagManager:
    async def search(self, request):
        content = "A long local evidence sentence. " * 300
        return {
            "query": request.query,
            "mode": request.mode.value if request.mode else "hybrid",
            "effectiveMode": "hybrid",
            "diagnostics": {
                "durationMs": 12,
                "resultCount": 10,
                "scoring": {
                    "strategy": "weighted_sum",
                    "textWeight": 0.3,
                    "vectorWeight": 0.7,
                    "formula": "score = textWeight * textScore + vectorWeight * vectorScore",
                },
            },
            "results": [
                {
                    "chunkId": f"chk_{idx}",
                    "documentId": f"doc_{idx}",
                    "collectionId": "default",
                    "sourceId": "src_docs",
                    "path": f"docs/{idx}.md",
                    "title": f"Doc {idx}",
                    "content": content,
                    "snippet": f"Snippet {idx}",
                    "score": 0.9,
                    "textScore": 0.8,
                    "vectorScore": 0.95,
                    "retrievalMode": "hybrid",
                    "sourceKind": "rag",
                    "sourceStatus": "active",
                    "untrustedEvidence": True,
                    "citation": {"label": f"[来源：docs/{idx}.md]", "path": f"docs/{idx}.md"},
                    "metadata": {
                        "untrustedEvidence": True,
                        "scoreBreakdown": {
                            "textWeight": 0.3,
                            "vectorWeight": 0.7,
                        },
                    },
                }
                for idx in range(10)
            ],
        }

    async def show(self, **_kwargs):
        return {
            "content": "expanded local document content",
            "truncated": False,
            "citation": {"label": "[来源：guide.md]"},
            "sourceKind": "rag",
            "untrustedEvidence": True,
        }


def test_rag_tools_are_visible_to_non_owner_agents():
    registry = ToolRegistry()
    create_rag_tools(rag_manager=FakeRagManager(), registry=registry)

    owner_defs = registry.to_tool_definitions(
        ToolContext(is_owner=True, caller_kind=CallerKind.AGENT)
    )
    non_owner_defs = registry.to_tool_definitions(
        ToolContext(is_owner=False, caller_kind=CallerKind.AGENT)
    )

    assert {tool.name for tool in owner_defs} >= {"rag_search", "rag_get"}
    assert {tool.name for tool in non_owner_defs} >= {"rag_search", "rag_get"}


@pytest.mark.asyncio
async def test_rag_search_tool_marks_untrusted_evidence():
    registry = ToolRegistry()
    create_rag_tools(rag_manager=FakeRagManager(), registry=registry)
    registered = registry.get("rag_search")

    payload = json.loads(await registered.handler(query="guide", mode="fts"))

    assert payload["source_kind"] == "rag"
    assert payload["untrusted_evidence"] is True
    assert payload["resultFormat"] == "evidence_text"
    assert "results" not in payload
    assert payload["text"].startswith('<external-content source="rag://local">')
    assert "[来源：guide.md]" in payload["text"]
    assert "local document content" in payload["text"]


@pytest.mark.asyncio
async def test_rag_search_tool_omits_mode_to_use_configured_default():
    registry = ToolRegistry()
    manager = FakeRagManager()
    create_rag_tools(rag_manager=manager, registry=registry)
    registered = registry.get("rag_search")

    payload = json.loads(await registered.handler(query="guide"))

    assert payload["mode"] is None
    assert manager.search_requests[-1].mode is None


@pytest.mark.asyncio
async def test_rag_search_tool_respects_explicit_mode_override():
    registry = ToolRegistry()
    manager = FakeRagManager()
    create_rag_tools(rag_manager=manager, registry=registry)
    registered = registry.get("rag_search")

    payload = json.loads(await registered.handler(query="guide", mode="vector_only"))

    assert payload["mode"] == "vector_only"
    assert manager.search_requests[-1].mode is RagRetrievalMode.VECTOR_ONLY


@pytest.mark.asyncio
async def test_rag_search_tool_returns_evidence_text_with_strict_budget():
    registry = ToolRegistry()
    create_rag_tools(rag_manager=LargeRagManager(), registry=registry)
    registered = registry.get("rag_search")

    raw = await registered.handler(query="guide", limit=50)
    payload = json.loads(raw)

    assert len(raw) <= 8000
    assert payload["resultFormat"] == "evidence_text"
    assert payload["payloadBudget"]["maxChars"] == 8000
    assert payload["payloadBudget"]["actualChars"] <= 8000
    assert payload["resultCount"] == 10
    assert payload["originalResultCount"] == 10
    assert payload["availableResultCount"] == 10
    assert payload["returnedResultCount"] == payload["evidenceBlockCount"]
    assert payload["evidenceResultCount"] == payload["returnedResultCount"]
    assert payload["returnedResultCount"] >= 1
    assert "results" not in payload
    assert "evidenceText" not in payload
    assert payload["text"].startswith('<external-content source="rag://local">')
    assert payload["text"].endswith("</external-content>")
    assert payload["length"] == payload["original_length"]
    assert payload["length"] > payload["returned_length"]
    assert payload["resultsTruncated"] is (
        payload["returnedResultCount"] < payload["availableResultCount"]
    )
    assert payload["contentTruncated"] is True
    assert "[1] RAG evidence" in payload["text"]
    assert "path: docs/0.md" in payload["text"]
    assert "chunk_id: chk_0" in payload["text"]
    assert "document_id: doc_0" in payload["text"]
    assert "citation: [来源：docs/0.md]" in payload["text"]
    assert "text_weight: 0.3" in payload["text"]
    assert "content_truncated: True" in payload["text"]
    assert "\n..." in payload["text"]


@pytest.mark.asyncio
async def test_rag_search_tool_preview_keeps_result_count_metadata_after_runtime_compaction():
    from opensquilla.engine.runtime import _json_tool_result_preview

    registry = ToolRegistry()
    create_rag_tools(rag_manager=LargeRagManager(), registry=registry)
    registered = registry.get("rag_search")

    raw = await registered.handler(query="guide", limit=50)
    payload = json.loads(raw)
    preview = json.loads(_json_tool_result_preview(payload, len(raw), 2000))

    assert len(raw) > 2000
    assert preview["result_truncated"] is True
    assert preview["result_original_chars"] == len(raw)
    assert preview["availableResultCount"] == 10
    assert preview["resultCount"] == 10
    assert preview["returnedResultCount"] >= 1
    assert preview["evidenceResultCount"] == preview["returnedResultCount"]
    assert preview["evidenceBlockCount"] == preview["returnedResultCount"]
    assert "results" not in preview
    assert "text" in preview
    assert len(preview["text"]) < len(payload["text"])


def test_rag_tool_budget_class_is_local():
    registry = ToolRegistry()
    create_rag_tools(rag_manager=FakeRagManager(), registry=registry)

    assert registry.get("rag_search").spec.result_budget_class == "local"
    assert registry.get("rag_get").spec.result_budget_class == "local"
