# Knowledge Retrieval Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make OpenSquilla preview discover and use retrieval profiles exposed by `opensquilla-knowledge-preview`, without hard-coding vector/hybrid modes in the frontend and without changing U1-U4.

**Architecture:** `opensquilla-knowledge-preview` will add `retrievalProfiles` and `defaultRetrievalProfile` to the existing `/v1/status` payload. OpenSquilla will keep using `knowledge.status` and `knowledge.search`; the Web UI derives retrieval options from status, while RPC/tool layers pass selected profile and embedding metadata through to the knowledge service.

**Tech Stack:** Python 3.12, pytest, Starlette service, OpenSquilla gateway RPC, Vue 3, TypeScript, Vitest, Vite.

---

## File Structure

Service capability contract:

- Modify `/root/Q3WORK/opensquilla-knowledge-preview/src/opensquilla_knowledge/manager.py`
  - Add helper functions to build retrieval profile status entries from `KnowledgeIndex.stats()`.
  - Add `retrievalProfiles` and `defaultRetrievalProfile` to `KnowledgeManager.status()`.
- Modify `/root/Q3WORK/opensquilla-knowledge-preview/tests/test_manager.py`
  - Add tests for no-index, FTS-only, and vector+hybrid available status payloads.

OpenSquilla gateway and tools:

- Modify `/root/Q3WORK/opensquilla-knowledge-rag-phase01/src/opensquilla/gateway/rpc_knowledge.py`
  - Merge `embeddingModel`, `embeddingDimensions`, `model`, and `dimensions` into search filters.
- Modify `/root/Q3WORK/opensquilla-knowledge-rag-phase01/tests/test_knowledge/test_rpc_knowledge.py`
  - Add a fake backend test proving search filter merge behavior.
- Modify `/root/Q3WORK/opensquilla-knowledge-rag-phase01/src/opensquilla/tools/builtin/knowledge_tools.py`
  - Add explicit `collection_id` and `retrieval_profile` parameters.
  - Merge `collection`, `collection_id`, and `retrieval_profile` into backend filters.
- Modify `/root/Q3WORK/opensquilla-knowledge-rag-phase01/tests/test_knowledge/test_tools.py`
  - Add a fake backend test proving tool filter merge behavior.
- Modify `/root/Q3WORK/opensquilla-knowledge-rag-phase01/tests/test_knowledge/test_http_backend.py`
  - Extend existing HTTP backend test to lock the `{query, topK, filters}` search contract.

Frontend retrieval helpers and UI:

- Create `/root/Q3WORK/opensquilla-knowledge-rag-phase01/opensquilla-webui/src/views/knowledgeRetrieval.ts`
  - Own retrieval profile fallback, default selection, search payload metadata, progress labels, and result score formatting.
- Create `/root/Q3WORK/opensquilla-knowledge-rag-phase01/opensquilla-webui/src/views/KnowledgeView.retrieval.test.ts`
  - Unit-test the helper functions without mounting the whole RAG page.
- Modify `/root/Q3WORK/opensquilla-knowledge-rag-phase01/opensquilla-webui/src/views/KnowledgeView.vue`
  - Use dynamic retrieval options from status.
  - Use `indexProfile` for ingest and selected retrieval profile for search.
  - Display vector/hybrid status and score fields.

Preview runtime:

- Modify `/srv/opensquilla-demo/instances/preview/runtime-gateway.toml`
  - Set `[knowledge].timeout_seconds = 90.0`.
- Do not modify U1-U4 runtime files or `/etc/systemd/system/opensquilla-demo@.service`.

## Task 0: Baseline And Branch Check

**Files:**
- Read: `/root/Q3WORK/opensquilla-knowledge-preview`
- Read: `/root/Q3WORK/opensquilla-knowledge-rag-phase01`

- [ ] **Step 1: Confirm current branches and clean worktrees**

Run:

```bash
ssh aliyun-ecs "cd /root/Q3WORK/opensquilla-knowledge-preview && git branch --show-current && git status --short && cd /root/Q3WORK/opensquilla-knowledge-rag-phase01 && git branch --show-current && git status --short"
```

Expected:

```text
knowledge-preview-dev
feature/knowledge-rag-phase01
```

No `git status --short` rows should appear after each branch name. If rows appear, inspect them before editing and do not revert unrelated user changes.

- [ ] **Step 2: Run targeted baseline tests**

Run:

```bash
ssh aliyun-ecs "cd /root/Q3WORK/opensquilla-knowledge-preview && .venv-preview/bin/python -m pytest tests/test_manager.py -q"
ssh aliyun-ecs "cd /root/Q3WORK/opensquilla-knowledge-rag-phase01 && .venv/bin/python -m pytest tests/test_knowledge/test_rpc_knowledge.py tests/test_knowledge/test_tools.py tests/test_knowledge/test_http_backend.py -q"
ssh aliyun-ecs "cd /root/Q3WORK/opensquilla-knowledge-rag-phase01/opensquilla-webui && npm run test:unit -- KnowledgeView"
```

Expected:

- `tests/test_manager.py` passes.
- The three OpenSquilla Python test files pass.
- `npm run test:unit -- KnowledgeView` may report no matching tests before `KnowledgeView.retrieval.test.ts` exists. Treat "no matching tests" as a baseline observation, not a failure.

## Task 1: Add Retrieval Profile Status To opensquilla-knowledge

**Files:**
- Modify: `/root/Q3WORK/opensquilla-knowledge-preview/tests/test_manager.py`
- Modify: `/root/Q3WORK/opensquilla-knowledge-preview/src/opensquilla_knowledge/manager.py`

- [ ] **Step 1: Write failing tests for status retrieval profiles**

Append these tests near the existing manager search/vector tests in `tests/test_manager.py`:

```python
def _profiles_by_id(status: dict[str, object]) -> dict[str, dict[str, object]]:
    profiles = status["retrievalProfiles"]
    assert isinstance(profiles, list)
    return {str(profile["id"]): dict(profile) for profile in profiles}


def test_status_reports_retrieval_profiles_without_indexes(tmp_path: Path) -> None:
    manager = KnowledgeManager(tmp_path / "knowledge")

    status = manager.status()
    profiles = _profiles_by_id(status)

    assert status["defaultRetrievalProfile"] == "sqlite_fts5_default"
    assert profiles["sqlite_fts5_default"] == {
        "id": "sqlite_fts5_default",
        "label": "SQLite FTS5",
        "kind": "lexical",
        "available": False,
        "reason": "fts_index_empty",
    }
    assert profiles["vector_bge_m3_1024"] == {
        "id": "vector_bge_m3_1024",
        "label": "Vector bge-m3",
        "kind": "vector",
        "available": False,
        "reason": "vector_index_empty",
        "model": "baai/bge-m3",
        "dimensions": 1024,
    }
    assert profiles["hybrid_rrf_bge_m3_fts5"] == {
        "id": "hybrid_rrf_bge_m3_fts5",
        "label": "Hybrid RRF",
        "kind": "hybrid",
        "available": False,
        "reason": "fts_or_vector_index_empty",
        "model": "baai/bge-m3",
        "dimensions": 1024,
    }


def test_status_reports_vector_and_hybrid_profiles_when_embeddings_exist(
    tmp_path: Path,
) -> None:
    manager = KnowledgeManager(tmp_path / "knowledge")
    _add_search_fixture(manager)

    status = manager.status()
    profiles = _profiles_by_id(status)

    assert profiles["sqlite_fts5_default"]["available"] is True
    assert profiles["sqlite_fts5_default"]["reason"] is None
    assert profiles["vector_bge_m3_3"] == {
        "id": "vector_bge_m3_3",
        "label": "Vector bge-m3",
        "kind": "vector",
        "available": True,
        "reason": None,
        "model": "baai/bge-m3",
        "dimensions": 3,
    }
    assert profiles["hybrid_rrf_bge_m3_fts5"] == {
        "id": "hybrid_rrf_bge_m3_fts5",
        "label": "Hybrid RRF",
        "kind": "hybrid",
        "available": True,
        "reason": None,
        "model": "baai/bge-m3",
        "dimensions": 3,
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
ssh aliyun-ecs "cd /root/Q3WORK/opensquilla-knowledge-preview && .venv-preview/bin/python -m pytest tests/test_manager.py::test_status_reports_retrieval_profiles_without_indexes tests/test_manager.py::test_status_reports_vector_and_hybrid_profiles_when_embeddings_exist -q"
```

Expected:

```text
The two tests fail with KeyError: 'retrievalProfiles'
```

- [ ] **Step 3: Add retrieval profile helper functions**

In `src/opensquilla_knowledge/manager.py`, add these helpers after `_empty_search_response()`:

```python
def _vector_retrieval_profile(model: str, dimensions: int) -> str:
    if model == _DEFAULT_EMBEDDING_MODEL:
        return f"vector_bge_m3_{dimensions}"
    model_token = re.sub(r"[^A-Za-z0-9_]+", "_", model).strip("_") or "model"
    return f"vector_{model_token}_{dimensions}"


def _retrieval_profiles_from_stats(stats: dict[str, Any]) -> dict[str, Any]:
    fts_available = int(stats.get("ftsChunksIndexed") or 0) > 0
    vector_available = int(stats.get("vectorChunksIndexed") or 0) > 0
    model = str(stats.get("embeddingModel") or _DEFAULT_EMBEDDING_MODEL)
    try:
        dimensions = int(stats.get("embeddingDimensions") or _DEFAULT_EMBEDDING_DIMENSIONS)
    except (TypeError, ValueError, OverflowError):
        dimensions = _DEFAULT_EMBEDDING_DIMENSIONS

    return {
        "defaultRetrievalProfile": _LEXICAL_RETRIEVAL_PROFILE,
        "retrievalProfiles": [
            {
                "id": _LEXICAL_RETRIEVAL_PROFILE,
                "label": "SQLite FTS5",
                "kind": "lexical",
                "available": fts_available,
                "reason": None if fts_available else "fts_index_empty",
            },
            {
                "id": _vector_retrieval_profile(model, dimensions),
                "label": "Vector bge-m3",
                "kind": "vector",
                "available": vector_available,
                "reason": None if vector_available else "vector_index_empty",
                "model": model,
                "dimensions": dimensions,
            },
            {
                "id": _HYBRID_RETRIEVAL_PROFILE,
                "label": "Hybrid RRF",
                "kind": "hybrid",
                "available": fts_available and vector_available,
                "reason": None
                if fts_available and vector_available
                else "fts_or_vector_index_empty",
                "model": model,
                "dimensions": dimensions,
            },
        ],
    }
```

- [ ] **Step 4: Include profiles in `KnowledgeManager.status()`**

Replace the end of `KnowledgeManager.status()` with:

```python
        stats = self._stats_with_available_vector_profile(self.index.stats())
        retrieval_profiles = _retrieval_profiles_from_stats(stats)
        return {
            "ok": True,
            "rootDir": str(self.root_dir),
            "dataDir": str(self.data_dir),
            "manifestPath": str(self.data_dir / "sample_manifest.jsonl"),
            "questionsPath": str(self.eval_dir / "golden_queries.jsonl"),
            "pipeline": "analyze-plan-execute-trace",
            "defaultSourceRoot": str(_DEFAULT_SOURCE_ROOT),
            **stats,
            **retrieval_profiles,
        }
```

- [ ] **Step 5: Run tests to verify they pass**

Run:

```bash
ssh aliyun-ecs "cd /root/Q3WORK/opensquilla-knowledge-preview && .venv-preview/bin/python -m pytest tests/test_manager.py::test_status_reports_retrieval_profiles_without_indexes tests/test_manager.py::test_status_reports_vector_and_hybrid_profiles_when_embeddings_exist -q"
```

Expected:

```text
2 passed
```

- [ ] **Step 6: Run all knowledge-preview tests**

Run:

```bash
ssh aliyun-ecs "cd /root/Q3WORK/opensquilla-knowledge-preview && .venv-preview/bin/python -m pytest tests -q"
```

Expected:

```text
passed
```

No failures.

- [ ] **Step 7: Commit service status contract**

Run:

```bash
ssh aliyun-ecs "cd /root/Q3WORK/opensquilla-knowledge-preview && git add src/opensquilla_knowledge/manager.py tests/test_manager.py && git commit -m 'feat: expose retrieval profiles in knowledge status'"
```

## Task 2: Pass Embedding Search Metadata Through Gateway RPC

**Files:**
- Modify: `/root/Q3WORK/opensquilla-knowledge-rag-phase01/tests/test_knowledge/test_rpc_knowledge.py`
- Modify: `/root/Q3WORK/opensquilla-knowledge-rag-phase01/src/opensquilla/gateway/rpc_knowledge.py`

- [ ] **Step 1: Write a failing RPC filter merge test**

Append this test to `tests/test_knowledge/test_rpc_knowledge.py`:

```python
@pytest.mark.asyncio
async def test_knowledge_rpc_search_merges_retrieval_and_embedding_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from opensquilla.gateway import rpc_knowledge as rpc_knowledge_module

    class RecordingKnowledgeBackend:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def search(
            self,
            query: str,
            *,
            top_k: int = 8,
            filters: dict[str, object] | None = None,
        ) -> dict[str, object]:
            self.calls.append(
                {
                    "query": query,
                    "top_k": top_k,
                    "filters": dict(filters or {}),
                }
            )
            return {"query": query, "results": [], "count": 0}

    backend = RecordingKnowledgeBackend()
    monkeypatch.setattr(
        rpc_knowledge_module,
        "manager_from_config",
        lambda _config: backend,
    )
    ctx = RpcContext(conn_id="test", config=SimpleNamespace())
    dispatcher = get_dispatcher()

    result = await dispatcher.dispatch(
        "search-profile",
        "knowledge.search",
        {
            "query": "苹果收入",
            "topK": 4,
            "filters": {
                "source": "goldman",
                "retrievalProfile": "sqlite_fts5_default",
                "embeddingDimensions": 768,
            },
            "collectionId": "datasets",
            "retrievalProfile": "hybrid_rrf_bge_m3_fts5",
            "embeddingModel": "baai/bge-m3",
            "embeddingDimensions": 1024,
        },
        ctx,
    )

    assert result.ok is True
    assert backend.calls == [
        {
            "query": "苹果收入",
            "top_k": 4,
            "filters": {
                "source": "goldman",
                "collectionId": "datasets",
                "retrievalProfile": "hybrid_rrf_bge_m3_fts5",
                "embeddingModel": "baai/bge-m3",
                "embeddingDimensions": 1024,
            },
        }
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
ssh aliyun-ecs "cd /root/Q3WORK/opensquilla-knowledge-rag-phase01 && .venv/bin/python -m pytest tests/test_knowledge/test_rpc_knowledge.py::test_knowledge_rpc_search_merges_retrieval_and_embedding_filters -q"
```

Expected:

```text
The test fails because 'embeddingModel' is missing from backend.calls[0]["filters"]
```

- [ ] **Step 3: Add a search filter merge helper**

In `src/opensquilla/gateway/rpc_knowledge.py`, add this helper after `_top_k()`:

```python
def _search_filters(params: dict[str, Any]) -> dict[str, Any] | None:
    filters = params.get("filters")
    if filters is not None and not isinstance(filters, dict):
        raise ValueError("params.filters must be an object")
    merged: dict[str, Any] = dict(filters or {})
    for key in (
        "collectionId",
        "retrievalProfile",
        "embeddingModel",
        "model",
        "embeddingDimensions",
        "dimensions",
    ):
        value = params.get(key)
        if value is not None and value != "":
            merged[key] = value
    return merged or None
```

- [ ] **Step 4: Use the helper in `_handle_knowledge_search()`**

Replace the filter handling block in `_handle_knowledge_search()` with:

```python
    filters = _search_filters(params)
    return _manager(ctx).search(query, top_k=_top_k(params), filters=filters)
```

Keep the query validation above it unchanged.

- [ ] **Step 5: Run RPC tests**

Run:

```bash
ssh aliyun-ecs "cd /root/Q3WORK/opensquilla-knowledge-rag-phase01 && .venv/bin/python -m pytest tests/test_knowledge/test_rpc_knowledge.py -q"
```

Expected:

```text
passed
```

No failures.

## Task 3: Expose Retrieval Profile And Collection ID In Agent Tool

**Files:**
- Modify: `/root/Q3WORK/opensquilla-knowledge-rag-phase01/tests/test_knowledge/test_tools.py`
- Modify: `/root/Q3WORK/opensquilla-knowledge-rag-phase01/src/opensquilla/tools/builtin/knowledge_tools.py`

- [ ] **Step 1: Write a failing tool filter merge test**

Append this test to `tests/test_knowledge/test_tools.py`:

```python
@pytest.mark.asyncio
async def test_knowledge_search_tool_merges_collection_and_retrieval_filters() -> None:
    class RecordingKnowledgeBackend:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def search(
            self,
            query: str,
            *,
            top_k: int = 8,
            filters: dict[str, object] | None = None,
        ) -> dict[str, object]:
            self.calls.append(
                {
                    "query": query,
                    "top_k": top_k,
                    "filters": dict(filters or {}),
                }
            )
            return {"query": query, "results": [], "count": 0}

        def status(self) -> dict[str, object]:
            return {"ok": True, "retrievalProfiles": []}

        def get(self, *, chunk_id=None, document_id=None):
            return None

    backend = RecordingKnowledgeBackend()
    registry = ToolRegistry()
    create_knowledge_tools(manager=backend, registry=registry)
    search_tool = registry.get("knowledge_search")
    assert search_tool is not None

    payload = json.loads(
        await search_tool.handler(
            query="苹果收入",
            top_k=5,
            collection="legacy",
            collection_id="datasets",
            retrieval_profile="hybrid_rrf_bge_m3_fts5",
            filters={
                "source": "goldman",
                "collectionId": "old",
                "retrievalProfile": "sqlite_fts5_default",
            },
        )
    )

    assert payload["count"] == 0
    assert backend.calls == [
        {
            "query": "苹果收入",
            "top_k": 5,
            "filters": {
                "source": "goldman",
                "collectionId": "datasets",
                "retrievalProfile": "hybrid_rrf_bge_m3_fts5",
            },
        }
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
ssh aliyun-ecs "cd /root/Q3WORK/opensquilla-knowledge-rag-phase01 && .venv/bin/python -m pytest tests/test_knowledge/test_tools.py::test_knowledge_search_tool_merges_collection_and_retrieval_filters -q"
```

Expected:

```text
The test fails with TypeError: unexpected keyword argument 'collection_id'
```

- [ ] **Step 3: Add a tool filter merge helper**

In `src/opensquilla/tools/builtin/knowledge_tools.py`, add this helper above `create_knowledge_tools()`:

```python
def _merged_search_filters(
    *,
    filters: dict[str, Any] | None,
    collection: str | None,
    collection_id: str | None,
    retrieval_profile: str | None,
) -> dict[str, Any] | None:
    merged: dict[str, Any] = dict(filters or {})
    resolved_collection = str(collection_id or collection or "").strip()
    if resolved_collection:
        merged["collectionId"] = resolved_collection
    resolved_profile = str(retrieval_profile or "").strip()
    if resolved_profile:
        merged["retrievalProfile"] = resolved_profile
    return merged or None
```

- [ ] **Step 4: Extend the `knowledge_search` tool schema**

In the `knowledge_search` tool `params`, add these entries after `collection`:

```python
            "collection_id": {
                "type": "string",
                "description": (
                    "Optional collection id to filter search results. Overrides collection "
                    "when both are provided."
                ),
            },
            "retrieval_profile": {
                "type": "string",
                "description": (
                    "Optional retrieval profile id. Call knowledge_status first and use one "
                    "of status.retrievalProfiles where available=true. Common ids include "
                    "sqlite_fts5_default, vector_bge_m3_1024, and hybrid_rrf_bge_m3_fts5."
                ),
            },
```

Update the `filters` description to:

```python
                "description": (
                    "Optional metadata filters such as source or contentKind. collection_id "
                    "and retrieval_profile are merged into this object when provided."
                ),
```

- [ ] **Step 5: Extend the handler signature and call backend with merged filters**

Replace the `knowledge_search` signature and backend call with:

```python
    async def knowledge_search(
        query: str,
        collection: str | None = None,
        collection_id: str | None = None,
        retrieval_profile: str | None = None,
        filters: dict[str, Any] | None = None,
        top_k: int = 8,
    ) -> str:
        clean_query = str(query or "").strip()
        if not clean_query:
            raise ToolError("query is required")
        merged_filters = _merged_search_filters(
            filters=filters,
            collection=collection,
            collection_id=collection_id,
            retrieval_profile=retrieval_profile,
        )
        payload = resolved_manager.search(clean_query, top_k=top_k, filters=merged_filters)
        if collection:
            payload["collection"] = collection
        return json.dumps(payload, ensure_ascii=False)
```

- [ ] **Step 6: Update `knowledge_status` description**

Change the `knowledge_status` tool description to:

```python
        description=(
            "Check the local document knowledge base status, including available "
            "retrievalProfiles when the backend exposes them. Use this before "
            "knowledge_search when selecting lexical, vector, or hybrid retrieval."
        ),
```

- [ ] **Step 7: Run tool tests**

Run:

```bash
ssh aliyun-ecs "cd /root/Q3WORK/opensquilla-knowledge-rag-phase01 && .venv/bin/python -m pytest tests/test_knowledge/test_tools.py -q"
```

Expected:

```text
passed
```

No failures.

## Task 4: Lock The HTTP Search Contract

**Files:**
- Modify: `/root/Q3WORK/opensquilla-knowledge-rag-phase01/tests/test_knowledge/test_http_backend.py`

- [ ] **Step 1: Extend the existing HTTP backend test**

In `test_http_knowledge_backend_calls_standalone_api()`, change the search call to:

```python
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
```

Change the expected `/v1/search` request body to:

```python
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
```

- [ ] **Step 2: Run HTTP backend test**

Run:

```bash
ssh aliyun-ecs "cd /root/Q3WORK/opensquilla-knowledge-rag-phase01 && .venv/bin/python -m pytest tests/test_knowledge/test_http_backend.py -q"
```

Expected:

```text
passed
```

This test should pass without production changes because `HttpKnowledgeBackend.search()` already forwards filters.

- [ ] **Step 3: Run all OpenSquilla knowledge tests and commit gateway/tool changes**

Run:

```bash
ssh aliyun-ecs "cd /root/Q3WORK/opensquilla-knowledge-rag-phase01 && .venv/bin/python -m pytest tests/test_knowledge/test_rpc_knowledge.py tests/test_knowledge/test_tools.py tests/test_knowledge/test_http_backend.py -q"
```

Expected:

```text
passed
```

No failures.

Run:

```bash
ssh aliyun-ecs "cd /root/Q3WORK/opensquilla-knowledge-rag-phase01 && git add src/opensquilla/gateway/rpc_knowledge.py src/opensquilla/tools/builtin/knowledge_tools.py tests/test_knowledge/test_rpc_knowledge.py tests/test_knowledge/test_tools.py tests/test_knowledge/test_http_backend.py && git commit -m 'feat: pass knowledge retrieval profiles through gateway'"
```

## Task 5: Add Frontend Retrieval Helper Tests

**Files:**
- Create: `/root/Q3WORK/opensquilla-knowledge-rag-phase01/opensquilla-webui/src/views/knowledgeRetrieval.ts`
- Create: `/root/Q3WORK/opensquilla-knowledge-rag-phase01/opensquilla-webui/src/views/KnowledgeView.retrieval.test.ts`

- [ ] **Step 1: Write failing frontend helper tests**

Create `opensquilla-webui/src/views/KnowledgeView.retrieval.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import {
  buildSearchProfilePayload,
  defaultRetrievalProfileId,
  formatResultScoreMeta,
  formatResultScorePrimary,
  retrievalProfilesFromStatus,
  searchProgressLabel,
} from './knowledgeRetrieval'

describe('knowledge retrieval helpers', () => {
  it('uses service retrievalProfiles when status exposes them', () => {
    const profiles = retrievalProfilesFromStatus({
      retrievalProfiles: [
        {
          id: 'sqlite_fts5_default',
          label: 'SQLite FTS5',
          kind: 'lexical',
          available: true,
          reason: null,
        },
        {
          id: 'hybrid_rrf_bge_m3_fts5',
          label: 'Hybrid RRF',
          kind: 'hybrid',
          available: true,
          reason: null,
          model: 'baai/bge-m3',
          dimensions: 1024,
        },
      ],
    })

    expect(profiles.map((profile) => profile.id)).toEqual([
      'sqlite_fts5_default',
      'hybrid_rrf_bge_m3_fts5',
    ])
  })

  it('falls back to FTS when status has no retrievalProfiles', () => {
    expect(retrievalProfilesFromStatus({}).map((profile) => profile.id)).toEqual([
      'sqlite_fts5_default',
    ])
  })

  it('selects service default when it is available', () => {
    expect(
      defaultRetrievalProfileId({
        defaultRetrievalProfile: 'hybrid_rrf_bge_m3_fts5',
        retrievalProfiles: [
          {
            id: 'sqlite_fts5_default',
            label: 'SQLite FTS5',
            kind: 'lexical',
            available: true,
            reason: null,
          },
          {
            id: 'hybrid_rrf_bge_m3_fts5',
            label: 'Hybrid RRF',
            kind: 'hybrid',
            available: true,
            reason: null,
            model: 'baai/bge-m3',
            dimensions: 1024,
          },
        ],
      }),
    ).toBe('hybrid_rrf_bge_m3_fts5')
  })

  it('skips disabled service default and selects first available profile', () => {
    expect(
      defaultRetrievalProfileId({
        defaultRetrievalProfile: 'hybrid_rrf_bge_m3_fts5',
        retrievalProfiles: [
          {
            id: 'sqlite_fts5_default',
            label: 'SQLite FTS5',
            kind: 'lexical',
            available: true,
            reason: null,
          },
          {
            id: 'hybrid_rrf_bge_m3_fts5',
            label: 'Hybrid RRF',
            kind: 'hybrid',
            available: false,
            reason: 'fts_or_vector_index_empty',
            model: 'baai/bge-m3',
            dimensions: 1024,
          },
        ],
      }),
    ).toBe('sqlite_fts5_default')
  })

  it('builds search payload with selected embedding metadata', () => {
    expect(
      buildSearchProfilePayload(
        {
          retrievalProfiles: [
            {
              id: 'hybrid_rrf_bge_m3_fts5',
              label: 'Hybrid RRF',
              kind: 'hybrid',
              available: true,
              reason: null,
              model: 'baai/bge-m3',
              dimensions: 1024,
            },
          ],
        },
        'hybrid_rrf_bge_m3_fts5',
      ),
    ).toEqual({
      retrievalProfile: 'hybrid_rrf_bge_m3_fts5',
      embeddingModel: 'baai/bge-m3',
      embeddingDimensions: 1024,
    })
  })

  it('formats hybrid and vector scores', () => {
    expect(
      formatResultScorePrimary(
        {
          score: 0.022529,
          fusionScore: 0.022529,
          retrievalProfile: 'hybrid_rrf_bge_m3_fts5',
        },
        'sqlite_fts5_default',
      ),
    ).toBe('fusion 0.023')
    expect(
      formatResultScoreMeta(
        {
          score: 0.022529,
          bm25Rank: -12.34567,
          vectorRank: 4,
          vectorScore: 0.78912,
          fusionScore: 0.022529,
          retrievalProfile: 'hybrid_rrf_bge_m3_fts5',
        },
        'sqlite_fts5_default',
      ),
    ).toEqual(['BM25 -12.346', 'Vector #4', 'Vector score 0.789'])
  })

  it('uses embedding retrieval label for vector and hybrid searches', () => {
    expect(
      searchProgressLabel(
        {
          retrievalProfiles: [
            {
              id: 'vector_bge_m3_1024',
              label: 'Vector bge-m3',
              kind: 'vector',
              available: true,
              reason: null,
              model: 'baai/bge-m3',
              dimensions: 1024,
            },
          ],
        },
        'vector_bge_m3_1024',
      ),
    ).toBe('Embedding retrieval')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
ssh aliyun-ecs "cd /root/Q3WORK/opensquilla-knowledge-rag-phase01/opensquilla-webui && npm run test:unit -- KnowledgeView.retrieval"
```

Expected:

```text
The test fails with Failed to resolve import "./knowledgeRetrieval"
```

- [ ] **Step 3: Implement `knowledgeRetrieval.ts`**

Create `opensquilla-webui/src/views/knowledgeRetrieval.ts`:

```ts
export type RetrievalKind = 'lexical' | 'vector' | 'hybrid'

export interface RetrievalProfileStatus {
  id: string
  label: string
  kind: RetrievalKind
  available: boolean
  reason: string | null
  model?: string
  dimensions?: number
}

export interface KnowledgeStatusLike {
  retrievalProfiles?: RetrievalProfileStatus[]
  defaultRetrievalProfile?: string
}

export interface KnowledgeResultScoreLike {
  score?: number | null
  bm25Rank?: number | null
  vectorRank?: number | null
  vectorScore?: number | null
  fusionScore?: number | null
  retrievalProfile?: string | null
}

export interface SearchProfilePayload {
  retrievalProfile: string
  embeddingModel?: string
  embeddingDimensions?: number
}

export const FALLBACK_RETRIEVAL_PROFILE: RetrievalProfileStatus = {
  id: 'sqlite_fts5_default',
  label: 'SQLite FTS5',
  kind: 'lexical',
  available: true,
  reason: null,
}

export function retrievalProfilesFromStatus(
  status: KnowledgeStatusLike | null | undefined,
): RetrievalProfileStatus[] {
  const profiles = status?.retrievalProfiles?.filter((profile) => profile?.id)
  return profiles?.length ? profiles : [FALLBACK_RETRIEVAL_PROFILE]
}

export function selectedRetrievalProfile(
  status: KnowledgeStatusLike | null | undefined,
  profileId: string,
): RetrievalProfileStatus {
  return (
    retrievalProfilesFromStatus(status).find((profile) => profile.id === profileId)
    || FALLBACK_RETRIEVAL_PROFILE
  )
}

export function defaultRetrievalProfileId(
  status: KnowledgeStatusLike | null | undefined,
  currentProfileId = '',
): string {
  const profiles = retrievalProfilesFromStatus(status)
  if (currentProfileId && profiles.some((profile) => profile.id === currentProfileId)) {
    return currentProfileId
  }
  const serviceDefault = status?.defaultRetrievalProfile
  if (
    serviceDefault
    && profiles.some((profile) => profile.id === serviceDefault && profile.available)
  ) {
    return serviceDefault
  }
  return profiles.find((profile) => profile.available)?.id || FALLBACK_RETRIEVAL_PROFILE.id
}

export function buildSearchProfilePayload(
  status: KnowledgeStatusLike | null | undefined,
  profileId: string,
): SearchProfilePayload {
  const profile = selectedRetrievalProfile(status, profileId)
  return {
    retrievalProfile: profile.id,
    ...(profile.model ? { embeddingModel: profile.model } : {}),
    ...(profile.dimensions ? { embeddingDimensions: profile.dimensions } : {}),
  }
}

export function searchProgressLabel(
  status: KnowledgeStatusLike | null | undefined,
  profileId: string,
): string {
  const profile = selectedRetrievalProfile(status, profileId)
  return profile.kind === 'vector' || profile.kind === 'hybrid'
    ? 'Embedding retrieval'
    : 'Searching'
}

export function formatResultScorePrimary(
  result: KnowledgeResultScoreLike,
  fallbackProfileId: string,
): string {
  const retrieval = result.retrievalProfile || fallbackProfileId
  if (retrieval.startsWith('vector_')) {
    return `vector ${fixedScore(result.vectorScore ?? result.score)}`
  }
  if (retrieval === 'hybrid_rrf_bge_m3_fts5') {
    return `fusion ${fixedScore(result.fusionScore ?? result.score)}`
  }
  return `lexical ${fixedScore(result.score)}`
}

export function formatResultScoreMeta(
  result: KnowledgeResultScoreLike,
  fallbackProfileId: string,
): string[] {
  const retrieval = result.retrievalProfile || fallbackProfileId
  const meta: string[] = []
  if (retrieval === 'hybrid_rrf_bge_m3_fts5' || retrieval === 'sqlite_fts5_default') {
    if (result.bm25Rank !== null && result.bm25Rank !== undefined) {
      meta.push(`BM25 ${fixedScore(result.bm25Rank)}`)
    }
  }
  if (retrieval.startsWith('vector_') || retrieval === 'hybrid_rrf_bge_m3_fts5') {
    if (result.vectorRank !== null && result.vectorRank !== undefined) {
      meta.push(`Vector #${result.vectorRank}`)
    }
    if (result.vectorScore !== null && result.vectorScore !== undefined) {
      meta.push(`Vector score ${fixedScore(result.vectorScore)}`)
    }
  }
  return meta
}

function fixedScore(value: number | null | undefined): string {
  return Number(value || 0).toFixed(3)
}
```

- [ ] **Step 4: Run helper tests**

Run:

```bash
ssh aliyun-ecs "cd /root/Q3WORK/opensquilla-knowledge-rag-phase01/opensquilla-webui && npm run test:unit -- KnowledgeView.retrieval"
```

Expected:

```text
KnowledgeView.retrieval.test.ts passes
```

## Task 6: Wire Dynamic Retrieval Into KnowledgeView

**Files:**
- Modify: `/root/Q3WORK/opensquilla-knowledge-rag-phase01/opensquilla-webui/src/views/KnowledgeView.vue`

- [ ] **Step 1: Import helpers and extend local types**

In `KnowledgeView.vue`, add this import near existing imports:

```ts
import {
  buildSearchProfilePayload,
  defaultRetrievalProfileId,
  formatResultScoreMeta,
  formatResultScorePrimary,
  retrievalProfilesFromStatus,
  searchProgressLabel,
} from './knowledgeRetrieval'
import type { RetrievalProfileStatus } from './knowledgeRetrieval'
```

Extend `KnowledgeStatus`:

```ts
  vectorChunksIndexed?: number
  vectorCoveragePct?: number
  embeddingModel?: string
  embeddingDimensions?: number
  embeddingWarnings?: string[]
  retrievalWarnings?: string[]
  retrievalProfiles?: RetrievalProfileStatus[]
  defaultRetrievalProfile?: string
```

Extend `KnowledgeResult`:

```ts
  vectorRank?: number | null
  vectorScore?: number | null
  fusionScore?: number | null
```

- [ ] **Step 2: Split index profile from retrieval profile**

Replace:

```ts
const retrievalProfile = ref('sqlite_fts5_default')
```

with:

```ts
const indexProfile = ref('sqlite_fts5_default')
const retrievalProfile = ref('sqlite_fts5_default')
```

Add these computed values near the existing computed values:

```ts
const retrievalProfiles = computed(() => retrievalProfilesFromStatus(status.value))
const activeRetrievalProfile = computed(() => (
  retrievalProfiles.value.find((profile) => profile.id === retrievalProfile.value)
  || retrievalProfiles.value[0]
))
const embeddingHint = computed(() => {
  const model = status.value?.embeddingModel
  const dimensions = status.value?.embeddingDimensions
  return model && dimensions ? `${model} · ${dimensions}d` : 'not indexed'
})
const vectorCoverageLabel = computed(() => {
  const coverage = status.value?.vectorCoveragePct
  return coverage === null || coverage === undefined ? '-' : `${Number(coverage).toFixed(1)}%`
})
const searchActionLabel = computed(() => (
  searching.value ? searchProgressLabel(status.value, retrievalProfile.value) : 'Search'
))
```

- [ ] **Step 3: Update status load to choose a valid default retrieval profile**

Replace `loadStatus()` with:

```ts
async function loadStatus(): Promise<void> {
  await rpc.waitForConnection()
  status.value = await rpc.call<KnowledgeStatus>('knowledge.status', {})
  retrievalProfile.value = defaultRetrievalProfileId(status.value, retrievalProfile.value)
}
```

- [ ] **Step 4: Update ingest payload to use `indexProfile`**

In `prepareSample()`, replace:

```ts
      indexProfiles: [retrievalProfile.value],
```

with:

```ts
      indexProfiles: [indexProfile.value],
```

- [ ] **Step 5: Update search payload to include selected profile metadata**

In `runSearch()`, replace:

```ts
      retrievalProfile: retrievalProfile.value,
```

with:

```ts
      ...buildSearchProfilePayload(status.value, retrievalProfile.value),
```

- [ ] **Step 6: Update retrieval select template**

Replace the single-option `<select v-model="retrievalProfile" class="control-input">` block with:

```vue
            <select v-model="retrievalProfile" class="control-input">
              <option
                v-for="profile in retrievalProfiles"
                :key="profile.id"
                :value="profile.id"
                :disabled="!profile.available"
              >
                {{ profile.label }}{{ profile.available ? '' : ` (${profile.reason || 'unavailable'})` }}
              </option>
            </select>
```

- [ ] **Step 7: Update status metrics for vector and embedding visibility**

In `statusMetrics`, keep the existing `RAG`, `Files`, `Chunks`, and `Tools` metric objects. Replace the current `Questions` metric object with `Vector`, and replace the current `Index` metric object with `Embedding`. The final array still has six entries:

```ts
  {
    label: 'Vector',
    value: vectorCoverageLabel.value,
    hint: 'Embedding coverage',
    className: Number(status.value?.vectorCoveragePct || 0) >= 99
      ? 'control-stat--accent'
      : '',
  },
  {
    label: 'Embedding',
    value: status.value?.embeddingModel ? 'Ready' : 'Missing',
    hint: embeddingHint.value,
    className: status.value?.embeddingModel ? 'control-stat--accent' : 'control-stat--warn',
  },
```

- [ ] **Step 8: Update result score rendering**

Replace:

```vue
                <span class="rag-result__score">
                  lexical {{ fixed(result.score) }}
                </span>
```

with:

```vue
                <span class="rag-result__score">
                  {{ formatResultScorePrimary(result, retrievalProfile) }}
                </span>
```

After the existing `Retrieval` meta span, add:

```vue
                <span
                  v-for="meta in formatResultScoreMeta(result, retrievalProfile)"
                  :key="`${result.chunkId}-${meta}`"
                >
                  <strong>{{ meta.split(' ')[0] }}</strong>{{ meta.split(' ').slice(1).join(' ') }}
                </span>
```

Remove the old dedicated BM25 meta span to avoid duplicate BM25 output.

- [ ] **Step 9: Update search button label**

Replace:

```vue
              <span>{{ searching ? 'Searching' : 'Search' }}</span>
```

with:

```vue
              <span>{{ searchActionLabel }}</span>
```

- [ ] **Step 10: Run frontend retrieval tests and typecheck**

Run:

```bash
ssh aliyun-ecs "cd /root/Q3WORK/opensquilla-knowledge-rag-phase01/opensquilla-webui && npm run test:unit -- KnowledgeView.retrieval && npm run typecheck"
```

Expected:

```text
KnowledgeView.retrieval.test.ts passes
vue-tsc --noEmit
```

No TypeScript errors.

- [ ] **Step 11: Build static assets**

Run:

```bash
ssh aliyun-ecs "cd /root/Q3WORK/opensquilla-knowledge-rag-phase01/opensquilla-webui && npm run build"
```

Expected:

```text
vite build
```

Exit code 0. The build writes updated static assets under `/root/Q3WORK/opensquilla-knowledge-rag-phase01/src/opensquilla/gateway/static/dist`.

- [ ] **Step 12: Commit frontend changes**

Run:

```bash
ssh aliyun-ecs "cd /root/Q3WORK/opensquilla-knowledge-rag-phase01 && git add opensquilla-webui/src/views/KnowledgeView.vue opensquilla-webui/src/views/knowledgeRetrieval.ts opensquilla-webui/src/views/KnowledgeView.retrieval.test.ts src/opensquilla/gateway/static/dist && git commit -m 'feat: discover knowledge retrieval profiles in UI'"
```

## Task 7: Preview Runtime Timeout And Service Verification

**Files:**
- Modify: `/srv/opensquilla-demo/instances/preview/runtime-gateway.toml`
- Read: `/srv/opensquilla-demo/instances/u1/runtime-gateway.toml`
- Read: `/srv/opensquilla-demo/instances/u2/runtime-gateway.toml`
- Read: `/srv/opensquilla-demo/instances/u3/runtime-gateway.toml`
- Read: `/srv/opensquilla-demo/instances/u4/runtime-gateway.toml`

- [ ] **Step 1: Update preview timeout only**

Run:

```bash
ssh aliyun-ecs "python3 - <<'PY'
from pathlib import Path

path = Path('/srv/opensquilla-demo/instances/preview/runtime-gateway.toml')
text = path.read_text(encoding='utf-8')
old = 'timeout_seconds = 30.0'
new = 'timeout_seconds = 90.0'
if old not in text:
    raise SystemExit('preview timeout_seconds = 30.0 not found')
path.write_text(text.replace(old, new, 1), encoding='utf-8')
PY"
```

- [ ] **Step 2: Verify preview changed and U1-U4 did not**

Run:

```bash
ssh aliyun-ecs "grep -nA8 -B2 '^\\[knowledge\\]' /srv/opensquilla-demo/instances/preview/runtime-gateway.toml /srv/opensquilla-demo/instances/u1/runtime-gateway.toml /srv/opensquilla-demo/instances/u2/runtime-gateway.toml /srv/opensquilla-demo/instances/u3/runtime-gateway.toml /srv/opensquilla-demo/instances/u4/runtime-gateway.toml"
```

Expected:

- preview has `endpoint = "http://127.0.0.1:18766"` and `timeout_seconds = 90.0`.
- u1, u2, u3, and u4 still have `endpoint = "http://127.0.0.1:18765"` and `timeout_seconds = 30.0`.

- [ ] **Step 3: Restart preview gateway only**

Run:

```bash
ssh aliyun-ecs "systemctl restart opensquilla-demo@preview && systemctl is-active opensquilla-demo@preview opensquilla-demo@u1 opensquilla-demo@u2 opensquilla-demo@u3 opensquilla-demo@u4"
```

Expected:

```text
active
active
active
active
active
```

- [ ] **Step 4: Verify preview knowledge status exposes retrieval profiles**

Run:

```bash
ssh aliyun-ecs "python3 - <<'PY'
import json
import urllib.request

with urllib.request.urlopen('http://127.0.0.1:18766/v1/status', timeout=10) as response:
    payload = json.load(response)
print(json.dumps({
    'defaultRetrievalProfile': payload.get('defaultRetrievalProfile'),
    'retrievalProfiles': payload.get('retrievalProfiles'),
    'vectorCoveragePct': payload.get('vectorCoveragePct'),
    'embeddingModel': payload.get('embeddingModel'),
    'embeddingDimensions': payload.get('embeddingDimensions'),
}, ensure_ascii=False, indent=2))
PY"
```

Expected:

- `defaultRetrievalProfile` is `sqlite_fts5_default`.
- `retrievalProfiles` contains entries for lexical, vector, and hybrid.
- preview reports `embeddingModel` as `baai/bge-m3` and `embeddingDimensions` as `1024`.

- [ ] **Step 5: Verify FTS search through preview knowledge**

Run:

```bash
ssh aliyun-ecs "python3 - <<'PY'
import json
import urllib.request

req = urllib.request.Request(
    'http://127.0.0.1:18766/v1/search',
    data=json.dumps({
        'query': '苹果公司收入',
        'topK': 2,
        'filters': {
            'collectionId': 'datasets',
            'retrievalProfile': 'sqlite_fts5_default',
        },
    }).encode('utf-8'),
    headers={'Content-Type': 'application/json'},
    method='POST',
)
with urllib.request.urlopen(req, timeout=30) as response:
    payload = json.load(response)
print(json.dumps({
    'retrieval': payload.get('retrieval'),
    'count': payload.get('count'),
    'firstProfile': (payload.get('results') or [{}])[0].get('retrievalProfile'),
}, ensure_ascii=False, indent=2))
PY"
```

Expected:

```json
{
  "retrieval": "sqlite_fts5_default",
  "count": 2,
  "firstProfile": "sqlite_fts5_default"
}
```

Hybrid/vector may still be slow because query embedding depends on OpenRouter. Do not make low-latency hybrid a completion criterion for this plan.

## Task 8: Final Verification

**Files:**
- Read both Git repositories and preview runtime config.

- [ ] **Step 1: Run full targeted test suite**

Run:

```bash
ssh aliyun-ecs "cd /root/Q3WORK/opensquilla-knowledge-preview && .venv-preview/bin/python -m pytest tests -q"
ssh aliyun-ecs "cd /root/Q3WORK/opensquilla-knowledge-rag-phase01 && .venv/bin/python -m pytest tests/test_knowledge/test_rpc_knowledge.py tests/test_knowledge/test_tools.py tests/test_knowledge/test_http_backend.py -q"
ssh aliyun-ecs "cd /root/Q3WORK/opensquilla-knowledge-rag-phase01/opensquilla-webui && npm run test:unit -- KnowledgeView.retrieval && npm run typecheck && npm run build"
```

Expected:

- All pytest commands pass.
- Vitest command passes.
- `npm run typecheck` exits 0.
- `npm run build` exits 0.

- [ ] **Step 2: Confirm git status**

Run:

```bash
ssh aliyun-ecs "cd /root/Q3WORK/opensquilla-knowledge-preview && git status --short && git log -1 --oneline && cd /root/Q3WORK/opensquilla-knowledge-rag-phase01 && git status --short && git log -3 --oneline"
```

Expected:

- No uncommitted source changes in either repo.
- Latest `opensquilla-knowledge-preview` commit is `feat: expose retrieval profiles in knowledge status`.
- Latest OpenSquilla commits include gateway/tool and UI retrieval discovery commits.

- [ ] **Step 3: Confirm runtime isolation**

Run:

```bash
ssh aliyun-ecs "grep -nE 'OPENSQUILLA_KNOWLEDGE_ENDPOINT|PORT=' /srv/opensquilla-demo/instances/preview/env /srv/opensquilla-demo/instances/u1/env /srv/opensquilla-demo/instances/u2/env /srv/opensquilla-demo/instances/u3/env /srv/opensquilla-demo/instances/u4/env && grep -nA4 -B1 '^\\[knowledge\\]' /srv/opensquilla-demo/instances/preview/runtime-gateway.toml /srv/opensquilla-demo/instances/u1/runtime-gateway.toml /srv/opensquilla-demo/instances/u2/runtime-gateway.toml /srv/opensquilla-demo/instances/u3/runtime-gateway.toml /srv/opensquilla-demo/instances/u4/runtime-gateway.toml"
```

Expected:

- preview endpoint remains `http://127.0.0.1:18766`.
- U1-U4 endpoints remain `http://127.0.0.1:18765`.
- preview timeout is `90.0`.
- U1-U4 timeouts remain `30.0`.

## Self-Review Notes

- Spec coverage: the plan covers status capability discovery, frontend dynamic options, ingest/search profile separation, vector/hybrid result display, agent tool schema, RPC metadata pass-through, preview timeout, and U1-U4 isolation.
- Scope: the plan intentionally does not add `/v1/capabilities`, vector build jobs, embedding model changes, or a low-latency hybrid guarantee.
- Type consistency: `RetrievalProfileStatus`, `retrievalProfiles`, `defaultRetrievalProfile`, `retrievalProfile`, `embeddingModel`, and `embeddingDimensions` are named consistently across service status, frontend helper, RPC, and tool layers.
