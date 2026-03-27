from __future__ import annotations

from threading import Lock

from app.models import Resource, ResourceCreateRequest, ResourceStatus


class InMemoryResourceRepository:
    def __init__(self) -> None:
        self._lock = Lock()
        self._resources: dict[str, Resource] = {}

    def list_resources(self, status: ResourceStatus | None = None, resource_type: str | None = None) -> list[Resource]:
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

            resource = Resource(
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
