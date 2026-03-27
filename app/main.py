from __future__ import annotations

import logging

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.auth import AuthClaims, require_auth, require_role
from app.config import Settings, load_settings_from_env, resolve_app_env
from app.mongo_client import close_mongo, connect_mongo
from app.models import ResourceCreateRequest, ResourceStatus, ResourceStatusPatchRequest
from app.repository import InMemoryResourceRepository
from app.secrets_loader import load_prod_secrets
from app.valkey_client import close_valkey, connect_valkey


logger = logging.getLogger(__name__)


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
    app.state.resource_repo = InMemoryResourceRepository()
    app.state.mongo = connect_mongo_fn(settings)
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
    async def validation_exception_handler(_: Request, __: RequestValidationError) -> JSONResponse:  # noqa: ANN001
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"error": "Invalid request payload"})

    @app.get("/api/v1/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "resource-service", "environment": settings.app_env}

    @app.get("/api/v1/resources")
    async def list_resources(
        status_filter: ResourceStatus | None = Query(default=None, alias="status"),
        type_filter: str | None = Query(default=None, alias="type"),
        claims: AuthClaims = Depends(require_auth),
    ) -> dict[str, object]:
        resources = app.state.resource_repo.list_resources(status=status_filter, resource_type=type_filter)
        return {
            "message": "Resources fetched",
            "requested_by": claims.username,
            "items": [resource.model_dump(by_alias=True) for resource in resources],
        }

    @app.post("/api/v1/resources", status_code=status.HTTP_201_CREATED)
    async def create_resource(
        payload: ResourceCreateRequest,
        _: AuthClaims = Depends(require_role("admin")),
    ) -> dict[str, object]:
        try:
            resource = app.state.resource_repo.create_resource(payload)
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
        payload: ResourceStatusPatchRequest,
        _: AuthClaims = Depends(require_role("admin")),
    ) -> dict[str, object]:
        resource = app.state.resource_repo.set_status(resource_code, payload.status)
        if resource is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "Resource not found", "code": "RESOURCE_NOT_FOUND"},
            )
        return {
            "message": "Resource status updated",
            "item": resource.model_dump(by_alias=True),
        }

    @app.get("/api/v1/auth/context")
    async def auth_context(claims: AuthClaims = Depends(require_auth)) -> dict[str, object]:
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
