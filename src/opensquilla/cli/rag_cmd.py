"""CLI commands for local document RAG."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from opensquilla.cli.gateway_rpc import run_gateway_sync
from opensquilla.cli.output import print_json

rag_app = typer.Typer(help="Manage and search local document RAG sources.")


def _call(
    method: str,
    params: dict[str, Any] | None,
    *,
    json_output: bool,
    config_path: Path | None,
):
    async def _run(client):
        return await client.call(method, params or {})

    return run_gateway_sync(_run, json_output=json_output, config_path=config_path)


@rag_app.command("status")
def status(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON"),
    config_path: Path | None = typer.Option(None, "--config", help="Override config path."),
) -> None:
    payload = _call("rag.status", {}, json_output=json_output, config_path=config_path)
    if json_output:
        print_json(payload)
        return
    console = Console(width=140, force_terminal=False)
    table = Table(title="RAG status")
    table.add_column("enabled")
    table.add_column("mode")
    table.add_column("sources")
    table.add_column("documents")
    table.add_column("chunks")
    table.add_column("vector")
    table.add_row(
        "yes" if payload.get("enabled") else "no",
        str(payload.get("retrievalMode") or "-"),
        str((payload.get("counts") or {}).get("sources", 0)),
        str((payload.get("counts") or {}).get("documents", 0)),
        str((payload.get("counts") or {}).get("chunks", 0)),
        "yes" if (payload.get("vector") or {}).get("available") else "no",
    )
    console.print(table)


@rag_app.command("add")
def add(
    path: str = typer.Argument(..., help="Local source directory"),
    collection: str = typer.Option("default", "--collection", help="Collection id"),
    source_id: str | None = typer.Option(None, "--source-id", help="Source id"),
    name: str | None = typer.Option(None, "--name", help="Display name"),
    include: list[str] | None = typer.Option(None, "--include", help="Include glob"),
    exclude: list[str] | None = typer.Option(None, "--exclude", help="Exclude glob"),
    index: bool = typer.Option(False, "--index", help="Run sync after add"),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON"),
    config_path: Path | None = typer.Option(None, "--config", help="Override config path."),
) -> None:
    payload = _call(
        "rag.add",
        {
            "path": path,
            "collectionId": collection,
            "sourceId": source_id,
            "name": name,
            "include": include or [],
            "exclude": exclude or [],
            "index": index,
        },
        json_output=json_output,
        config_path=config_path,
    )
    if json_output:
        print_json(payload)
        return
    source = payload.get("source") or {}
    Console(force_terminal=False).print(
        f"{'created' if payload.get('created') else 'updated'} "
        f"{source.get('sourceId')} ({source.get('status')})"
    )


@rag_app.command("sources")
def sources(
    collection: str | None = typer.Option(None, "--collection", help="Collection id"),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON"),
    config_path: Path | None = typer.Option(None, "--config", help="Override config path."),
) -> None:
    payload = _call(
        "rag.list",
        {"kind": "sources", "collectionId": collection},
        json_output=json_output,
        config_path=config_path,
    )
    if json_output:
        print_json(payload)
        return
    table = Table(title="RAG sources")
    table.add_column("source")
    table.add_column("collection")
    table.add_column("status")
    table.add_column("enabled")
    table.add_column("path")
    for source in payload.get("items") or []:
        table.add_row(
            str(source.get("sourceId")),
            str(source.get("collectionId")),
            str(source.get("status")),
            "yes" if source.get("enabled") else "no",
            str(source.get("path")),
        )
    Console(width=160, force_terminal=False).print(table)


@rag_app.command("documents")
def documents(
    source_id: str | None = typer.Option(None, "--source-id", help="Source id"),
    limit: int = typer.Option(100, "--limit", help="Limit"),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON"),
    config_path: Path | None = typer.Option(None, "--config", help="Override config path."),
) -> None:
    payload = _call(
        "rag.list",
        {"kind": "documents", "sourceId": source_id, "limit": limit},
        json_output=json_output,
        config_path=config_path,
    )
    if json_output:
        print_json(payload)
        return
    table = Table(title="RAG documents")
    table.add_column("document")
    table.add_column("source")
    table.add_column("status")
    table.add_column("path")
    for doc in payload.get("items") or []:
        table.add_row(
            str(doc.get("documentId")),
            str(doc.get("sourceId")),
            str(doc.get("status")),
            str(doc.get("path")),
        )
    Console(width=160, force_terminal=False).print(table)


@rag_app.command("sync")
def sync(
    source_id: str | None = typer.Option(None, "--source-id", help="Source id"),
    collection: str | None = typer.Option(None, "--collection", help="Collection id"),
    force: bool = typer.Option(False, "--force", help="Force reindex"),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON"),
    config_path: Path | None = typer.Option(None, "--config", help="Override config path."),
) -> None:
    payload = _call(
        "rag.sync",
        {"sourceId": source_id, "collectionId": collection, "force": force},
        json_output=json_output,
        config_path=config_path,
    )
    if json_output:
        print_json(payload)
        return
    table = Table(title="RAG sync jobs")
    table.add_column("job")
    table.add_column("source")
    table.add_column("status")
    table.add_column("seen")
    table.add_column("indexed")
    table.add_column("failed")
    for job in payload.get("jobs") or []:
        table.add_row(
            str(job.get("jobId")),
            str(job.get("sourceId")),
            str(job.get("status")),
            str(job.get("filesSeen")),
            str(job.get("filesIndexed")),
            str(job.get("filesFailed")),
        )
    Console(width=140, force_terminal=False).print(table)


@rag_app.command("reindex")
def reindex(
    source_id: str | None = typer.Option(None, "--source-id", help="Source id"),
    collection: str | None = typer.Option(None, "--collection", help="Collection id"),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON"),
    config_path: Path | None = typer.Option(None, "--config", help="Override config path."),
) -> None:
    payload = _call(
        "rag.reindex",
        {"sourceId": source_id, "collectionId": collection},
        json_output=json_output,
        config_path=config_path,
    )
    if json_output:
        print_json(payload)
        return
    Console(force_terminal=False).print(f"{len(payload.get('jobs') or [])} reindex job(s) finished")


@rag_app.command("search")
def search(
    query: str = typer.Argument(..., help="Search query"),
    mode: str = typer.Option("hybrid", "--mode", help="hybrid, fts, or vector_only"),
    limit: int = typer.Option(8, "--limit", help="Limit"),
    path_prefix: str | None = typer.Option(None, "--path-prefix", help="Relative path prefix"),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON"),
    config_path: Path | None = typer.Option(None, "--config", help="Override config path."),
) -> None:
    payload = _call(
        "rag.search",
        {"query": query, "mode": mode, "limit": limit, "pathPrefix": path_prefix},
        json_output=json_output,
        config_path=config_path,
    )
    if json_output:
        print_json(payload)
        return
    table = Table(title="RAG search")
    table.add_column("score")
    table.add_column("path")
    table.add_column("citation")
    table.add_column("snippet")
    for result in payload.get("results") or []:
        table.add_row(
            f"{float(result.get('score') or 0.0):.3f}",
            str(result.get("path")),
            str((result.get("citation") or {}).get("label")),
            str(result.get("snippet")),
        )
    Console(width=160, force_terminal=False).print(table)


@rag_app.command("show")
def show(
    chunk_id: str | None = typer.Option(None, "--chunk-id", help="Chunk id"),
    document_id: str | None = typer.Option(None, "--document-id", help="Document id"),
    source_id: str | None = typer.Option(None, "--source-id", help="Source id"),
    path: str | None = typer.Option(None, "--path", help="Relative path"),
    max_chars: int = typer.Option(12000, "--max-chars", help="Maximum chars"),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON"),
    config_path: Path | None = typer.Option(None, "--config", help="Override config path."),
) -> None:
    payload = _call(
        "rag.show",
        {
            "chunkId": chunk_id,
            "documentId": document_id,
            "sourceId": source_id,
            "path": path,
            "maxChars": max_chars,
        },
        json_output=json_output,
        config_path=config_path,
    )
    if json_output:
        print_json(payload)
        return
    console = Console(width=140, force_terminal=False)
    console.print(str((payload.get("citation") or {}).get("label") or ""))
    console.print(str(payload.get("content") or ""))
