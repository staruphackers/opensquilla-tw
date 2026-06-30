from __future__ import annotations

import io
import zipfile

import pytest


def _zip_bytes(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


class FakeRagManager:
    def __init__(self) -> None:
        self.calls = []

    async def import_zip_source(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "source": {
                "sourceId": "src_import_docs_1234abcd",
                "collectionId": kwargs["collection_id"],
                "mode": "imported",
                "path": "/state/rag/imports/src_import_docs_1234abcd/files",
                "name": kwargs["name"],
                "status": "stale",
            },
            "created": True,
            "job": None,
            "import": {
                "archiveName": kwargs["archive_name"],
                "filesSeen": 1,
                "filesImported": 1,
                "filesSkipped": 0,
                "bytesImported": 5,
            },
        }


def test_rag_import_route_uploads_zip_to_manager() -> None:
    pytest.importorskip("starlette.testclient")
    from starlette.applications import Starlette
    from starlette.testclient import TestClient

    from opensquilla.gateway.config import GatewayConfig
    from opensquilla.gateway.rag_imports import register_rag_import_routes

    manager = FakeRagManager()
    app = Starlette(debug=False)
    register_rag_import_routes(app, config=GatewayConfig(), rag_manager=manager)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/rag/imports",
            data={"collectionId": "finance", "name": "Finance", "index": "true"},
            files={"file": ("finance.zip", _zip_bytes({"a.md": "alpha"}), "application/zip")},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source"]["mode"] == "imported"
    assert body["import"]["archiveName"] == "finance.zip"
    assert manager.calls[-1]["collection_id"] == "finance"
    assert manager.calls[-1]["name"] == "Finance"
    assert manager.calls[-1]["index"] is True


def test_rag_import_route_rejects_missing_file() -> None:
    pytest.importorskip("starlette.testclient")
    from starlette.applications import Starlette
    from starlette.testclient import TestClient

    from opensquilla.gateway.config import GatewayConfig
    from opensquilla.gateway.rag_imports import register_rag_import_routes

    app = Starlette(debug=False)
    register_rag_import_routes(app, config=GatewayConfig(), rag_manager=FakeRagManager())

    with TestClient(app) as client:
        response = client.post("/api/v1/rag/imports", data={"name": "No File"})

    assert response.status_code == 400


def test_rag_import_route_rejects_non_zip_upload() -> None:
    pytest.importorskip("starlette.testclient")
    from starlette.applications import Starlette
    from starlette.testclient import TestClient

    from opensquilla.gateway.config import GatewayConfig
    from opensquilla.gateway.rag_imports import register_rag_import_routes

    manager = FakeRagManager()
    app = Starlette(debug=False)
    register_rag_import_routes(app, config=GatewayConfig(), rag_manager=manager)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/rag/imports",
            files={"file": ("notes.txt", b"plain", "text/plain")},
        )

    assert response.status_code == 415
    assert manager.calls == []


def test_rag_import_route_requires_authorization_header_in_token_mode() -> None:
    pytest.importorskip("starlette.testclient")
    from starlette.applications import Starlette
    from starlette.testclient import TestClient

    from opensquilla.gateway.config import AuthConfig, GatewayConfig
    from opensquilla.gateway.middleware import AuthMiddleware
    from opensquilla.gateway.rag_imports import register_rag_import_routes

    config = GatewayConfig(auth=AuthConfig(mode="token", token="secret"))
    app = Starlette(debug=False)
    register_rag_import_routes(app, config=config, rag_manager=FakeRagManager())
    app.add_middleware(AuthMiddleware, config=config)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/rag/imports?token=secret",
            files={"file": ("docs.zip", _zip_bytes({"a.md": "alpha"}), "application/zip")},
        )

    assert response.status_code == 401
    assert "Authorization" in response.json()["error"]
