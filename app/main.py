from __future__ import annotations

import logging
from typing import Annotated, Any, TypeVar

from dotenv import load_dotenv
from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from app.auth import AuthClaims, require_auth, require_role
from app.config import Settings, load_settings_from_env, resolve_app_env
from app.models import (
    ResourceCreateRequest,
    ResourcePatchRequest,
    ResourceStatus,
    ResourceStatusPatchRequest,
)
from app.mongo_client import close_mongo, connect_mongo
from app.repository import create_resource_repository
from app.secrets_loader import load_prod_secrets
from app.valkey_client import close_valkey, connect_valkey

logger = logging.getLogger(__name__)
RequestModelT = TypeVar("RequestModelT", bound=BaseModel)
StatusFilter = Annotated[ResourceStatus | None, Query(alias="status")]
TypeFilter = Annotated[str | None, Query(alias="type")]
RequiredAuth = Annotated[AuthClaims, Depends(require_auth)]
AdminAuth = Annotated[AuthClaims, Depends(require_role("admin"))]


def serialize_validation_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "loc": list(error.get("loc", ())),
            "message": error.get("msg", "Invalid value"),
            "type": error.get("type", "value_error"),
        }
        for error in errors
    ]


def validation_error_summary(details: list[dict[str, Any]]) -> str:
    if not details:
        return "Invalid request payload"

    messages: list[str] = []
    for detail in details:
        loc = detail.get("loc", [])
        field = ".".join(str(part) for part in loc) if isinstance(loc, list) else str(loc)
        message = str(detail.get("message", "Invalid value"))
        messages.append(f"{field}: {message}" if field else message)

    return f"Invalid request payload: {'; '.join(messages)}"


def invalid_payload_detail(errors: list[dict[str, Any]]) -> dict[str, object]:
    details = serialize_validation_errors(errors)
    return {
        "error": validation_error_summary(details),
        "details": details,
    }


def validate_request_payload(model_type: type[RequestModelT], payload: Any) -> RequestModelT:
    try:
        return model_type.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=invalid_payload_detail(exc.errors()),
        ) from exc


def create_app(
    settings: Settings | None = None,
    load_prod_secrets_fn=load_prod_secrets,
    connect_mongo_fn=connect_mongo,
    connect_valkey_fn=connect_valkey,
) -> FastAPI:
    load_dotenv()

    if settings is None:
        if resolve_app_env() == "prod":
            load_prod_secrets_fn()
        settings = load_settings_from_env()

    app = FastAPI(title="NUS Resource Service", version="1.0.0")
    app.state.settings = settings
    app.state.mongo = connect_mongo_fn(settings)
    app.state.resource_repo = create_resource_repository(app.state.mongo, settings)
    app.state.valkey = connect_valkey_fn(settings)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
    )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:  # noqa: ANN001
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            payload = exc.detail
        elif isinstance(exc.detail, str):
            payload = {"error": exc.detail}
        else:
            payload = {"error": "Request failed"}
        return JSONResponse(status_code=exc.status_code, content=payload, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:  # noqa: ANN001
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=invalid_payload_detail(exc.errors()),
        )

    @app.get("/api/v1/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "resource-service", "environment": settings.app_env}

    @app.get("/api/v1/resources")
    async def list_resources(
        claims: RequiredAuth,
        status_filter: StatusFilter = None,
        type_filter: TypeFilter = None,
    ) -> dict[str, object]:
        resources = app.state.resource_repo.list_resources(
            status=status_filter, resource_type=type_filter
        )
        return {
            "message": "Resources fetched",
            "requested_by": claims.username,
            "items": [resource.model_dump(by_alias=True) for resource in resources],
        }

    @app.post("/api/v1/resources", status_code=status.HTTP_201_CREATED)
    async def create_resource(
        _: AdminAuth,
        payload: Annotated[Any, Body()],
    ) -> dict[str, object]:
        create_payload = validate_request_payload(ResourceCreateRequest, payload)
        try:
            resource = app.state.resource_repo.create_resource(create_payload)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": str(exc), "code": "RESOURCE_CONFLICT"},
            ) from exc

        return {
            "message": "Resource created",
            "item": resource.model_dump(by_alias=True),
        }

    @app.patch("/api/v1/resources/{resource_code}/status")
    async def patch_resource_status(
        resource_code: str,
        _: AdminAuth,
        payload: Annotated[Any, Body()],
    ) -> dict[str, object]:
        patch_payload = validate_request_payload(ResourceStatusPatchRequest, payload)
        resource = app.state.resource_repo.set_status(resource_code, patch_payload.status)
        if resource is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "Resource not found", "code": "RESOURCE_NOT_FOUND"},
            )
        return {
            "message": "Resource status updated",
            "item": resource.model_dump(by_alias=True),
        }

    @app.patch("/api/v1/resources/{resource_code}")
    async def patch_resource(
        resource_code: str,
        _: AdminAuth,
        payload: Annotated[Any, Body()],
    ) -> dict[str, object]:
        patch_payload = validate_request_payload(ResourcePatchRequest, payload)
        resource = app.state.resource_repo.update_resource(resource_code, patch_payload)
        if resource is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "Resource not found", "code": "RESOURCE_NOT_FOUND"},
            )
        return {
            "message": "Resource updated",
            "item": resource.model_dump(by_alias=True),
        }

    @app.get("/api/v1/auth/context")
    async def auth_context(claims: RequiredAuth) -> dict[str, object]:
        return {
            "message": "Authenticated",
            "user": {"username": claims.username, "role": claims.role},
        }

    @app.on_event("shutdown")
    async def shutdown_event() -> None:
        close_mongo(app.state.mongo)
        close_valkey(app.state.valkey)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    current_settings = app.state.settings
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(current_settings.port), reload=False)
