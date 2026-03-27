from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ResourceStatus = Literal["active", "inactive", "maintenance"]


class ResourceLocation(BaseModel):
    site: str = ""
    building: str = ""
    floor: str = ""
    room: str = ""
    timezone: str = "UTC"


class Resource(BaseModel):
    resource_code: str = Field(alias="resourceCode")
    name: str
    type: str
    status: ResourceStatus = "active"
    location: ResourceLocation = Field(default_factory=ResourceLocation)
    slot_duration_min: int = Field(default=30, alias="slotDurationMin")
    default_capacity: int = Field(default=1, alias="defaultCapacity")
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {
        "populate_by_name": True,
    }


class ResourceCreateRequest(BaseModel):
    resource_code: str = Field(alias="resourceCode", min_length=1)
    name: str = Field(min_length=1)
    type: str = Field(min_length=1)
    status: ResourceStatus = "active"
    location: ResourceLocation = Field(default_factory=ResourceLocation)
    slot_duration_min: int = Field(default=30, alias="slotDurationMin", ge=5)
    default_capacity: int = Field(default=1, alias="defaultCapacity", ge=1)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {
        "populate_by_name": True,
    }


class ResourceStatusPatchRequest(BaseModel):
    status: ResourceStatus
