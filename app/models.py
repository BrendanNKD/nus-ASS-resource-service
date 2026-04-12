from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


class ResourceLocationPatchRequest(BaseModel):
    site: str = Field(default=None)
    building: str = Field(default=None)
    floor: str = Field(default=None)
    room: str = Field(default=None)
    timezone: str = Field(default=None)

    model_config = ConfigDict(extra="forbid")


class ResourcePatchRequest(BaseModel):
    name: str = Field(default=None, min_length=1)
    type: str = Field(default=None, min_length=1)
    status: ResourceStatus = Field(default=None)
    location: ResourceLocationPatchRequest = Field(default=None)
    slot_duration_min: int = Field(default=None, alias="slotDurationMin", ge=5)
    default_capacity: int = Field(default=None, alias="defaultCapacity", ge=1)
    tags: list[str] = Field(default=None)
    metadata: dict[str, Any] = Field(default=None)

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    @model_validator(mode="after")
    def at_least_one_field(self) -> "ResourcePatchRequest":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self


class ResourceStatusPatchRequest(BaseModel):
    status: ResourceStatus
