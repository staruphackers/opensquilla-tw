from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal, overload

import httpx


def _payload_path(value: Path | str | None) -> str | None:
    return str(value) if value else None


class HttpKnowledgeBackend:
    """HTTP adapter for the standalone opensquilla-knowledge service."""

    def __init__(
        self,
        endpoint: str,
        *,
        api_key: str | None = None,
        api_key_env: str | None = None,
        timeout_seconds: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        resolved_key = api_key or (os.environ.get(api_key_env) if api_key_env else None)
        self.headers = {"Accept": "application/json"}
        if resolved_key:
            self.headers["Authorization"] = f"Bearer {resolved_key}"
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def status(self) -> dict[str, Any]:
        return self._request("GET", "/v1/status")

    def collections(self) -> dict[str, Any]:
        return self._request("GET", "/v1/collections")

    def prepare_sample(
        self,
        *,
        source_root: Path | str | None = None,
        limit: int = 60,
        collection_name: str | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/prepare-sample",
            json={
                "sourceRoot": _payload_path(source_root),
                "limit": limit,
                "collectionName": collection_name,
            },
        )

    def ingest_collection(
        self,
        *,
        source_root: Path | str | None = None,
        limit: int = 60,
        collection_name: str | None = None,
        collection_id: str | None = None,
        index_profiles: list[str] | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/ingest",
            json={
                "sourceRoot": _payload_path(source_root),
                "limit": limit,
                "collectionName": collection_name,
                "collectionId": collection_id,
                "indexProfiles": index_profiles,
            },
        )

    def search(
        self,
        query: str,
        *,
        top_k: int = 8,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/search",
            json={"query": query, "topK": top_k, "filters": filters or {}},
        )

    def get(
        self,
        *,
        chunk_id: str | None = None,
        document_id: str | None = None,
    ) -> dict[str, Any] | None:
        if chunk_id:
            return self._request("GET", f"/v1/chunks/{chunk_id}", missing_ok=True)
        if document_id:
            return self._request(
                "GET",
                "/v1/item",
                params={"documentId": document_id},
                missing_ok=True,
            )
        raise ValueError("chunk_id or document_id is required")

    def questions(self) -> dict[str, Any]:
        return self._request("GET", "/v1/questions")

    def record_judgment(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/v1/judgments", json=payload)

    @overload
    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        missing_ok: Literal[False] = False,
    ) -> dict[str, Any]: ...

    @overload
    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        missing_ok: Literal[True],
    ) -> dict[str, Any] | None: ...

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        missing_ok: bool = False,
    ) -> dict[str, Any] | None:
        with httpx.Client(
            base_url=self.endpoint,
            headers=self.headers,
            timeout=self.timeout_seconds,
            transport=self.transport,
        ) as client:
            response = client.request(method, path, json=json, params=params)
        if response.status_code == 404 and missing_ok:
            return None
        if response.status_code >= 400:
            raise RuntimeError(_error_message(response))
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("knowledge service returned a non-object JSON payload")
        return payload


def _error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict) and error.get("message"):
            return f"knowledge service {response.status_code}: {error['message']}"
    return f"knowledge service {response.status_code}: {response.text[:300]}"
