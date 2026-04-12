from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from pymongo.errors import DuplicateKeyError

from app.models import ResourceCreateRequest, ResourcePatchRequest
from app.repository import MongoResourceRepository


class FakeMongoCollection:
    def __init__(self) -> None:
        self.documents: dict[str, dict[str, Any]] = {}
        self.indexes: list[object] = []

    def create_index(self, key: object, unique: bool = False) -> None:
        self.indexes.append((key, unique))

    def insert_one(self, document: dict[str, Any]) -> None:
        resource_code = document["resourceCode"]
        if resource_code in self.documents:
            raise DuplicateKeyError("duplicate resource")
        self.documents[resource_code] = deepcopy(document)

    def find(self, query: dict[str, Any]) -> list[dict[str, Any]]:
        matches: list[dict[str, Any]] = []
        for document in self.documents.values():
            if all(document.get(key) == value for key, value in query.items()):
                matches.append(deepcopy(document))
        return matches

    def find_one(self, query: dict[str, Any]) -> dict[str, Any] | None:
        for document in self.find(query):
            return document
        return None

    def find_one_and_update(
        self,
        query: dict[str, Any],
        update: dict[str, dict[str, Any]],
        return_document: object,
    ) -> dict[str, Any] | None:
        del return_document
        resource_code = query["resourceCode"]
        document = self.documents.get(resource_code)
        if document is None:
            return None

        for field, value in update.get("$set", {}).items():
            target = document
            parts = field.split(".")
            for part in parts[:-1]:
                target = target.setdefault(part, {})
            target[parts[-1]] = value

        return deepcopy(document)


class FakeMongoDatabase:
    def __init__(self) -> None:
        self.resources = FakeMongoCollection()

    def __getitem__(self, name: str) -> FakeMongoCollection:
        assert name == "resources"
        return self.resources


def test_mongo_repository_persists_created_resources_across_instances():
    database = FakeMongoDatabase()
    first_repo = MongoResourceRepository(database)

    created = first_repo.create_resource(
        ResourceCreateRequest.model_validate(
            {
                "resourceCode": "ROOM_A101",
                "name": "Room A101",
                "type": "clinic",
                "defaultCapacity": 2,
            }
        )
    )

    second_repo = MongoResourceRepository(database)
    resources = second_repo.list_resources()

    assert created.resource_code == "ROOM_A101"
    assert [resource.resource_code for resource in resources] == ["ROOM_A101"]
    assert resources[0].default_capacity == 2


def test_mongo_repository_rejects_duplicate_resource_code():
    repo = MongoResourceRepository(FakeMongoDatabase())
    payload = ResourceCreateRequest.model_validate(
        {"resourceCode": "ROOM_A101", "name": "Room A101", "type": "clinic"}
    )

    repo.create_resource(payload)

    with pytest.raises(ValueError, match="Resource already exists"):
        repo.create_resource(payload)


def test_mongo_repository_partial_update_preserves_omitted_fields():
    repo = MongoResourceRepository(FakeMongoDatabase())
    repo.create_resource(
        ResourceCreateRequest.model_validate(
            {
                "resourceCode": "ROOM_A101",
                "name": "Room A101",
                "type": "clinic",
                "location": {
                    "site": "NUS",
                    "building": "University Health Centre",
                    "floor": "1",
                    "room": "A101",
                    "timezone": "Asia/Singapore",
                },
                "defaultCapacity": 2,
                "slotDurationMin": 30,
                "tags": ["room", "clinic"],
                "metadata": {"source": "test"},
            }
        )
    )

    updated = repo.update_resource(
        "ROOM_A101",
        ResourcePatchRequest.model_validate(
            {
                "defaultCapacity": 4,
                "location": {"room": "A102"},
            }
        ),
    )

    assert updated is not None
    assert updated.resource_code == "ROOM_A101"
    assert updated.name == "Room A101"
    assert updated.default_capacity == 4
    assert updated.slot_duration_min == 30
    assert updated.location.site == "NUS"
    assert updated.location.building == "University Health Centre"
    assert updated.location.floor == "1"
    assert updated.location.room == "A102"
    assert updated.location.timezone == "Asia/Singapore"
    assert updated.tags == ["room", "clinic"]
    assert updated.metadata == {"source": "test"}
