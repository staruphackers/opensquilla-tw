from __future__ import annotations

from types import SimpleNamespace

import pytest

from opensquilla.gateway.config import GatewayConfig, RagConfig, RagSourceConfig
from opensquilla.gateway.rpc import RpcContext, get_dispatcher
from opensquilla.gateway.scopes import METHOD_SCOPES


@pytest.mark.asyncio
async def test_rag_status_returns_disabled_when_manager_not_wired():
    ctx = RpcContext(conn_id="test", config=GatewayConfig(rag=RagConfig(enabled=False)))

    result = await get_dispatcher().dispatch("1", "rag.status", {}, ctx)

    assert result.ok
    assert result.payload["enabled"] is False


@pytest.mark.asyncio
async def test_rag_search_requires_manager_when_enabled():
    ctx = RpcContext(conn_id="test", config=GatewayConfig(rag=RagConfig(enabled=True)))

    result = await get_dispatcher().dispatch("1", "rag.search", {"query": "x"}, ctx)

    assert not result.ok
    assert result.error.code == "UNAVAILABLE"


@pytest.mark.asyncio
async def test_rag_rpc_delegates_search_to_manager():
    class FakeManager:
        async def search(self, request):
            return {"query": request.query, "results": []}

    ctx = RpcContext(
        conn_id="test",
        config=GatewayConfig(rag=RagConfig(enabled=True)),
        rag_manager=FakeManager(),
    )

    result = await get_dispatcher().dispatch("1", "rag.search", {"query": "hello"}, ctx)

    assert result.ok
    assert result.payload == {"query": "hello", "results": []}


@pytest.mark.asyncio
async def test_rag_browse_lists_directories_under_allowed_root(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text("hello", encoding="utf-8")
    ctx = RpcContext(
        conn_id="test",
        config=GatewayConfig(workspace_dir=str(tmp_path), rag=RagConfig(enabled=False)),
    )

    result = await get_dispatcher().dispatch(
        "1",
        "rag.browse",
        {"path": str(tmp_path)},
        ctx,
    )

    assert result.ok
    assert result.payload["current"] == str(tmp_path)
    assert result.payload["roots"][0]["name"] == "Workspace"
    assert result.payload["roots"][0]["kind"] == "workspace"
    assert result.payload["preview"]["supportedFiles"] == 1
    assert any(item["name"] == "docs" for item in result.payload["directories"])


@pytest.mark.asyncio
async def test_rag_browse_parent_allows_up_from_nested_root(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    ctx = RpcContext(
        conn_id="test",
        config=GatewayConfig(
            workspace_dir=str(tmp_path),
            rag=RagConfig(enabled=False, sources=[RagSourceConfig(path=str(docs))]),
        ),
    )

    result = await get_dispatcher().dispatch(
        "1",
        "rag.browse",
        {"path": str(docs)},
        ctx,
    )

    assert result.ok
    assert result.payload["current"] == str(docs)
    assert result.payload["parent"] == str(tmp_path)


@pytest.mark.asyncio
async def test_rag_browse_rejects_path_outside_allowed_roots(tmp_path):
    ctx = RpcContext(
        conn_id="test",
        config=GatewayConfig(workspace_dir=str(tmp_path), rag=RagConfig(enabled=False)),
    )

    result = await get_dispatcher().dispatch(
        "1",
        "rag.browse",
        {"path": "/etc"},
        ctx,
    )

    assert not result.ok
    assert result.error.code == "INVALID_REQUEST"


def test_rag_methods_have_explicit_scopes():
    for method in {
        "rag.status",
        "rag.browse",
        "rag.list",
        "rag.search",
        "rag.show",
        "rag.add",
        "rag.sync",
        "rag.reindex",
        "rag.enable_source",
        "rag.disable_source",
        "rag.remove_source",
    }:
        assert method in METHOD_SCOPES


def test_rpc_context_accepts_rag_manager():
    manager = SimpleNamespace()
    ctx = RpcContext(conn_id="test", rag_manager=manager)

    assert ctx.rag_manager is manager
