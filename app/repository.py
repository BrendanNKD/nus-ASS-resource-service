from __future__ import annotations

import logging
from copy import deepcopy
from threading import Lock
from typing import Any

from pymongo import ReturnDocument
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.config import Settings
from app.models import Resource, ResourceCreateRequest, ResourcePatchRequest, ResourceStatus

RESOURCE_COLLECTION = "resources"
logger = logging.getLogger(__name__)


def create_resource_repository(mongo_client: Any, settings: Settings):
    if mongo_client is None:
        return InMemoryResourceRepository()
    try:
        return MongoResourceRepository(mongo_client[settings.db.name])
    except PyMongoError as exc:
        if settings.app_env == "prod":
            raise RuntimeError("Unable to initialize Mongo resource repository") from exc
        logger.warning("Mongo resource repository unavailable; using in-memory storage: %s", exc)
        return InMemoryResourceRepository()


def resource_from_create_payload(payload: ResourceCreateRequest) -> Resource:
    return Resource(
        resourceCode=payload.resource_code,
        name=payload.name,
        type=payload.type,
        status=payload.status,
        location=payload.location,
        slotDurationMin=payload.slot_duration_min,
        defaultCapacity=payload.default_capacity,
        tags=payload.tags,
        metadata=payload.metadata,
    )


def resource_from_document(document: dict[str, Any]) -> Resource:
    payload = deepcopy(document)
    payload.pop("_id", None)
    return Resource.model_validate(payload)


def patch_payload_to_mongo_set(payload: ResourcePatchRequest) -> dict[str, Any]:
    patch = payload.model_dump(exclude_unset=True, by_alias=True)
    updates: dict[str, Any] = {}
    for field_name, value in patch.items():
        if field_name == "location":
            for location_field, location_value in value.items():
                updates[f"location.{location_field}"] = location_value
            continue

        updates[field_name] = value
    return updates


class InMemoryResourceRepository:
    def __init__(self) -> None:
        self._lock = Lock()
        self._resources: dict[str, Resource] = {}

    def list_resources(
        self, status: ResourceStatus | None = None, resource_type: str | None = None
    ) -> list[Resource]:
        with self._lock:
            values = list(self._resources.values())

        if status:
            values = [resource for resource in values if resource.status == status]
        if resource_type:
            values = [resource for resource in values if resource.type == resource_type]
        return values

    def create_resource(self, payload: ResourceCreateRequest) -> Resource:
        with self._lock:
            if payload.resource_code in self._resources:
                raise ValueError("Resource already exists")

            resource = resource_from_create_payload(payload)
            self._resources[payload.resource_code] = resource
            return resource

    def set_status(self, resource_code: str, status: ResourceStatus) -> Resource | None:
        with self._lock:
            current = self._resources.get(resource_code)
            if current is None:
                return None
            updated = current.model_copy(update={"status": status})
            self._resources[resource_code] = updated
            return updated

    def update_resource(self, resource_code: str, payload: ResourcePatchRequest) -> Resource | None:
        with self._lock:
            current = self._resources.get(resource_code)
            if current is None:
                return None

            updates: dict[str, object] = {}
            for field_name in payload.model_fields_set:
                if field_name == "location":
                    location_updates = payload.location.model_dump(exclude_unset=True)
                    updates["location"] = current.location.model_copy(update=location_updates)
                    continue

                updates[field_name] = getattr(payload, field_name)

            updated = current.model_copy(update=updates)
            self._resources[resource_code] = updated
            return updated


class MongoResourceRepository:
    def __init__(self, database: Database) -> None:
        self._collection = database[RESOURCE_COLLECTION]
        self._collection.create_index("resourceCode", unique=True)
        self._collection.create_index([("status", 1), ("type", 1)])

    def list_resources(
        self, status: ResourceStatus | None = None, resource_type: str | None = None
    ) -> list[Resource]:
        query: dict[str, Any] = {}
        if status:
            query["status"] = status
        if resource_type:
            query["type"] = resource_type

        return [resource_from_document(document) for document in self._collection.find(query)]

    def create_resource(self, payload: ResourceCreateRequest) -> Resource:
        resource = resource_from_create_payload(payload)
        document = resource.model_dump(by_alias=True)
        try:
            self._collection.insert_one(document)
        except DuplicateKeyError as exc:
            raise ValueError("Resource already exists") from exc
        return resource

    def set_status(self, resource_code: str, status: ResourceStatus) -> Resource | None:
        document = self._collection.find_one_and_update(
            {"resourceCode": resource_code},
            {"$set": {"status": status}},
            return_document=ReturnDocument.AFTER,
        )
        if document is None:
            return None
        return resource_from_document(document)

    def update_resource(self, resource_code: str, payload: ResourcePatchRequest) -> Resource | None:
        updates = patch_payload_to_mongo_set(payload)
        if not updates:
            document = self._collection.find_one({"resourceCode": resource_code})
        else:
            document = self._collection.find_one_and_update(
                {"resourceCode": resource_code},
                {"$set": updates},
                return_document=ReturnDocument.AFTER,
            )
        if document is None:
            return None
        return resource_from_document(document)
