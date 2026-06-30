"""RPC handlers for local document RAG."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from opensquilla.gateway.rpc import RpcContext, RpcHandlerError, RpcUnavailableError, get_dispatcher
from opensquilla.rag.errors import RagDisabledError, RagError, RagNotFoundError, RagValidationError
from opensquilla.rag.paths import DEFAULT_EXCLUDE_GLOBS, is_supported_text_extension
from opensquilla.rag.types import RagRetrievalMode, RagSearchRequest

_d = get_dispatcher()

_MAX_BROWSE_DIRS = 100
_MAX_PREVIEW_ENTRIES = 1200


def _params(params: Any) -> dict[str, Any]:
    if params is None:
        return {}
    if not isinstance(params, dict):
        raise RpcHandlerError("INVALID_REQUEST", "RAG params must be an object")
    return params


def _manager(ctx: RpcContext) -> Any:
    manager = getattr(ctx, "rag_manager", None)
    if manager is None:
        config = getattr(ctx, "config", None)
        if config is not None and not bool(getattr(getattr(config, "rag", None), "enabled", False)):
            raise RagDisabledError()
        raise RpcUnavailableError("RAG manager is not configured")
    return manager


def _raise_rpc(exc: RagError) -> None:
    if isinstance(exc, RagDisabledError):
        raise RpcHandlerError("RAG_DISABLED", exc.message, details=exc.to_dict())
    if isinstance(exc, RagNotFoundError):
        raise RpcHandlerError("NOT_FOUND", exc.message, details=exc.to_dict())
    if isinstance(exc, RagValidationError):
        raise RpcHandlerError("INVALID_REQUEST", exc.message, details=exc.to_dict())
    raise RpcHandlerError("RAG_ERROR", exc.message, details=exc.to_dict(), retryable=exc.retryable)


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        try:
            resolved = path.expanduser().resolve()
        except OSError:
            continue
        if not resolved.is_dir() or str(resolved) == "/":
            continue
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        result.append(resolved)
    return result


def _browse_roots(config: Any) -> list[dict[str, Any]]:
    candidates: list[tuple[Path, str, str]] = []
    workspace = getattr(config, "workspace_dir", None)
    if workspace:
        candidates.append((Path(str(workspace)), "Workspace", "workspace"))
    q3work = Path.home() / "Q3WORK"
    if q3work.is_dir():
        candidates.append((q3work, "Q3WORK", "common"))
    home = Path.home()
    if home.is_dir():
        candidates.append((home, "Home", "common"))
    config_path = getattr(config, "config_path", None)
    if config_path:
        candidates.append((Path(str(config_path)).expanduser().parent, "Config folder", "config"))
    cwd = Path.cwd()
    candidates.append((cwd, "Current checkout", "workspace"))
    if cwd.parent != cwd and str(cwd.parent) != "/":
        candidates.append((cwd.parent, "Parent of checkout", "workspace"))
    rag = getattr(config, "rag", None)
    for source in getattr(rag, "sources", []) or []:
        root_path = getattr(source, "path", None)
        if root_path:
            source_path = Path(str(root_path)).expanduser()
            name = (
                getattr(source, "name", None)
                or getattr(source, "source_id", None)
                or "Configured source"
            )
            candidates.append(
                (source_path if source_path.is_dir() else source_path.parent, str(name), "source")
            )
    paths = _dedupe_paths([path for path, _name, _kind in candidates])
    meta_by_path: dict[str, tuple[str, str]] = {}
    for path, name, kind in candidates:
        try:
            resolved = path.expanduser().resolve()
        except OSError:
            continue
        key = str(resolved)
        if key not in meta_by_path:
            meta_by_path[key] = (name, kind)
    return [
        {
            "name": meta_by_path.get(str(path), (path.name or str(path), "other"))[0],
            "kind": meta_by_path.get(str(path), (path.name or str(path), "other"))[1],
            "path": path,
        }
        for path in paths
    ]


def _browse_root_paths(roots: list[dict[str, Any]]) -> list[Path]:
    return [root["path"] for root in roots]


def _is_under_any_root(path: Path, roots: list[Path]) -> bool:
    for root in roots:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _resolve_browse_path(raw_path: str | None, roots: list[Path]) -> Path:
    if not roots:
        raise RpcHandlerError("UNAVAILABLE", "No RAG browse roots are available")
    if not raw_path:
        return roots[0]
    path = Path(raw_path).expanduser()
    try:
        resolved = path.resolve()
    except OSError as exc:
        raise RpcHandlerError("INVALID_REQUEST", f"Cannot resolve path: {raw_path}") from exc
    if not resolved.is_dir():
        raise RpcHandlerError("INVALID_REQUEST", "RAG browse path must be an existing directory")
    if not _is_under_any_root(resolved, roots):
        raise RpcHandlerError(
            "INVALID_REQUEST",
            "RAG browse path is outside allowed roots",
            details={"path": str(resolved), "roots": [str(root) for root in roots]},
        )
    return resolved


def _source_preview(path: Path) -> dict[str, Any]:
    supported = 0
    scanned = 0
    truncated = False
    excluded_names = {".git", ".hg", ".svn", "node_modules", ".venv", "venv", "__pycache__"}
    for root, dirs, files in os.walk(path):
        dirs[:] = [
            dirname
            for dirname in dirs
            if not dirname.startswith(".") and dirname not in excluded_names
        ]
        root_path = Path(root)
        if any(root_path.match(pattern.rstrip("/**")) for pattern in DEFAULT_EXCLUDE_GLOBS):
            dirs[:] = []
            continue
        for filename in files:
            scanned += 1
            if is_supported_text_extension(Path(filename).suffix):
                supported += 1
            if scanned >= _MAX_PREVIEW_ENTRIES:
                truncated = True
                return {
                    "supportedFiles": supported,
                    "scannedEntries": scanned,
                    "truncated": truncated,
                }
    return {"supportedFiles": supported, "scannedEntries": scanned, "truncated": truncated}


def _browse_directories(path: Path, roots: list[Path]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    try:
        children = sorted(path.iterdir(), key=lambda item: item.name.lower())
    except OSError:
        return items
    for child in children:
        if len(items) >= _MAX_BROWSE_DIRS:
            break
        if child.name.startswith("."):
            continue
        try:
            if not child.is_dir():
                continue
            resolved = child.resolve()
        except OSError:
            continue
        if not _is_under_any_root(resolved, roots):
            continue
        items.append(
            {
                "name": child.name,
                "path": str(resolved),
                "preview": _source_preview(resolved),
            }
        )
    return items


def _browse_parent(path: Path, roots: list[Path]) -> str | None:
    parent = path.parent
    if parent == path or not _is_under_any_root(parent, roots):
        return None
    return str(parent)


@_d.method("rag.status", scope="operator.read")
async def rag_status(params: Any, ctx: RpcContext) -> dict[str, Any]:
    _params(params)
    manager = getattr(ctx, "rag_manager", None)
    if manager is None:
        config = getattr(ctx, "config", None)
        if config is not None and not bool(getattr(getattr(config, "rag", None), "enabled", False)):
            return {"enabled": False, "reason": "rag_disabled"}
        raise RpcUnavailableError("RAG manager is not configured")
    return await manager.status()


@_d.method("rag.browse", scope="operator.read")
async def rag_browse(params: Any, ctx: RpcContext) -> dict[str, Any]:
    p = _params(params)
    config = getattr(ctx, "config", None)
    if config is None:
        raise RpcUnavailableError("Gateway config is not available")
    roots = _browse_roots(config)
    root_paths = _browse_root_paths(roots)
    current = _resolve_browse_path(p.get("path"), root_paths)
    return {
        "roots": [
            {"name": root["name"], "kind": root["kind"], "path": str(root["path"])}
            for root in roots
        ],
        "current": str(current),
        "parent": _browse_parent(current, root_paths),
        "preview": _source_preview(current),
        "directories": _browse_directories(current, root_paths),
    }


@_d.method("rag.add", scope="operator.write")
async def rag_add(params: Any, ctx: RpcContext) -> dict[str, Any]:
    p = _params(params)
    try:
        return await _manager(ctx).add_source(
            path=str(p.get("path") or "").strip(),
            collection_id=str(p.get("collectionId") or "default"),
            source_id=p.get("sourceId"),
            name=p.get("name"),
            include=p.get("include") or [],
            exclude=p.get("exclude") or [],
            enabled=bool(p.get("enabled", True)),
            index=bool(p.get("index", False)),
        )
    except RagError as exc:
        _raise_rpc(exc)
        raise AssertionError("unreachable")


@_d.method("rag.list", scope="operator.read")
async def rag_list(params: Any, ctx: RpcContext) -> dict[str, Any]:
    p = _params(params)
    kind = str(p.get("kind") or "sources")
    try:
        manager = _manager(ctx)
        if kind == "collections":
            return {
                "kind": "collections",
                "items": [
                    {
                        "collectionId": c.collection_id,
                        "name": c.name,
                        "enabled": c.enabled,
                        "metadata": c.metadata,
                        "createdAt": c.created_at,
                        "updatedAt": c.updated_at,
                    }
                    for c in await manager.store.list_collections()
                ],
            }
        if kind == "sources":
            return {
                "kind": "sources",
                "items": await manager.list_sources(
                    collection_id=p.get("collectionId"),
                    include_disabled=bool(p.get("includeDisabled", True)),
                ),
            }
        if kind == "documents":
            return await manager.list_documents(
                collection_id=p.get("collectionId"),
                source_id=p.get("sourceId"),
                status=p.get("status"),
                limit=int(p.get("limit") or 100),
                offset=int(p.get("offset") or 0),
            )
        if kind == "jobs":
            return await manager.list_jobs(limit=int(p.get("limit") or 20))
        if kind == "errors":
            return await manager.list_errors(
                limit=int(p.get("limit") or 100),
                source_id=p.get("sourceId"),
            )
        raise RagValidationError("Unsupported rag.list kind", details={"kind": kind})
    except RagError as exc:
        _raise_rpc(exc)
        raise AssertionError("unreachable")


@_d.method("rag.sync", scope="operator.write")
async def rag_sync(params: Any, ctx: RpcContext) -> dict[str, Any]:
    p = _params(params)
    try:
        return await _manager(ctx).sync(
            collection_id=p.get("collectionId"),
            source_id=p.get("sourceId"),
            force=bool(p.get("force", False)),
        )
    except RagError as exc:
        _raise_rpc(exc)
        raise AssertionError("unreachable")


@_d.method("rag.reindex", scope="operator.write")
async def rag_reindex(params: Any, ctx: RpcContext) -> dict[str, Any]:
    p = _params(params)
    if bool(p.get("vectorOnly", False)):
        raise RpcHandlerError(
            "INVALID_REQUEST",
            "rag.reindex(vectorOnly=true) is not supported yet",
        )
    return await rag_sync({**p, "force": True}, ctx)


@_d.method("rag.search", scope="operator.read")
async def rag_search(params: Any, ctx: RpcContext) -> dict[str, Any]:
    p = _params(params)
    mode_raw = p.get("mode")
    mode = RagRetrievalMode(mode_raw) if mode_raw else None
    try:
        return await _manager(ctx).search(
            RagSearchRequest(
                query=str(p.get("query") or ""),
                mode=mode,
                limit=int(p["limit"]) if p.get("limit") is not None else None,
                min_score=float(p["minScore"]) if p.get("minScore") is not None else None,
                collection_id=p.get("collectionId"),
                source_id=p.get("sourceId"),
                path_prefix=p.get("pathPrefix"),
            )
        )
    except RagError as exc:
        _raise_rpc(exc)
        raise AssertionError("unreachable")


@_d.method("rag.show", scope="operator.read")
async def rag_show(params: Any, ctx: RpcContext) -> dict[str, Any]:
    p = _params(params)
    try:
        return await _manager(ctx).show(
            chunk_id=p.get("chunkId"),
            document_id=p.get("documentId"),
            source_id=p.get("sourceId"),
            path=p.get("path"),
            max_chars=int(p.get("maxChars") or 12000),
        )
    except RagError as exc:
        _raise_rpc(exc)
        raise AssertionError("unreachable")


@_d.method("rag.disable_source", scope="operator.write")
async def rag_disable_source(params: Any, ctx: RpcContext) -> dict[str, Any]:
    p = _params(params)
    try:
        return await _manager(ctx).disable_source(str(p.get("sourceId") or ""))
    except RagError as exc:
        _raise_rpc(exc)
        raise AssertionError("unreachable")


@_d.method("rag.enable_source", scope="operator.write")
async def rag_enable_source(params: Any, ctx: RpcContext) -> dict[str, Any]:
    p = _params(params)
    try:
        return await _manager(ctx).enable_source(str(p.get("sourceId") or ""))
    except RagError as exc:
        _raise_rpc(exc)
        raise AssertionError("unreachable")


@_d.method("rag.remove_source", scope="operator.write")
async def rag_remove_source(params: Any, ctx: RpcContext) -> dict[str, Any]:
    p = _params(params)
    try:
        return await _manager(ctx).remove_source(
            str(p.get("sourceId") or ""),
            delete_index=bool(p.get("deleteIndex", True)),
        )
    except RagError as exc:
        _raise_rpc(exc)
        raise AssertionError("unreachable")
