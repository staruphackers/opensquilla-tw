"""HTTP multipart routes for persistent RAG source imports."""

from __future__ import annotations

from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from opensquilla.gateway.config import GatewayConfig
from opensquilla.gateway.uploads import _extract_authorization_token
from opensquilla.rag.errors import RagDisabledError, RagError, RagValidationError


def register_rag_import_routes(
    app: Starlette,
    *,
    config: GatewayConfig,
    rag_manager: Any,
) -> None:
    """Register POST /api/v1/rag/imports on the given Starlette app."""

    async def import_handler(request: Request) -> JSONResponse:
        if config.auth.mode == "token":
            if config.auth.token and _extract_authorization_token(request) != config.auth.token:
                return JSONResponse(
                    {
                        "error": (
                            "Authorization header (Bearer …) required for "
                            "/api/v1/rag/imports"
                        ),
                        "code": "UNAUTHORIZED",
                    },
                    status_code=401,
                )

        if rag_manager is None:
            return JSONResponse(
                {"error": "RAG unavailable", "code": "RAG_UNAVAILABLE"},
                status_code=503,
            )

        try:
            form = await request.form()
        except Exception as exc:
            return JSONResponse(
                {"error": f"multipart/form-data required: {exc}", "code": "BAD_REQUEST"},
                status_code=400,
            )

        upload = form.get("file")
        if upload is None or not hasattr(upload, "read"):
            return JSONResponse(
                {"error": "missing 'file' multipart field", "code": "BAD_REQUEST"},
                status_code=400,
            )

        filename = str(getattr(upload, "filename", None) or "source.zip").strip()
        if not filename.lower().endswith(".zip"):
            return JSONResponse(
                {
                    "error": "RAG import upload must be a .zip file",
                    "code": "UNSUPPORTED_MEDIA_TYPE",
                },
                status_code=415,
            )

        payload = await upload.read()
        if not isinstance(payload, bytes) or not payload:
            return JSONResponse(
                {"error": "empty upload", "code": "BAD_REQUEST"},
                status_code=400,
            )

        try:
            result = await rag_manager.import_zip_source(
                archive_name=filename,
                payload=payload,
                collection_id=_form_str(form.get("collectionId"), default="default"),
                name=_form_optional_str(form.get("name")),
                index=_form_bool(form.get("index"), default=False),
            )
        except RagDisabledError as exc:
            return JSONResponse({"error": exc.message, "code": exc.code}, status_code=503)
        except RagValidationError as exc:
            return JSONResponse(
                {"error": exc.message, "code": exc.code, "details": exc.details},
                status_code=_status_for_validation_error(exc),
            )
        except RagError as exc:
            return JSONResponse(
                {"error": exc.message, "code": exc.code, "details": exc.details},
                status_code=500 if exc.retryable else 400,
            )

        return JSONResponse(result)

    app.router.routes.append(
        Route("/api/v1/rag/imports", import_handler, methods=["POST"])
    )


def _form_str(value: object, *, default: str) -> str:
    if value is None:
        return default
    cleaned = str(value).strip()
    return cleaned or default


def _form_optional_str(value: object) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _form_bool(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _status_for_validation_error(exc: RagValidationError) -> int:
    message = exc.message.lower()
    if "too large" in message:
        return 413
    if "valid zip" in message or ".zip" in message:
        return 415
    return 400
