# Resource Service Endpoint Update Request

This document describes the resource service changes needed to support the current admin room-management UI.

The frontend already supports:

- Creating a bookable room with `resourceCode`, `name`, `type`, `location`, `slotDurationMin`, and `defaultCapacity`.
- Listing resources with `GET /api/v1/resources`.
- Updating resource status with `PATCH /api/v1/resources/{resourceCode}/status`.

The missing backend capability is editing an existing room after creation, especially updating its capacity.

## Auth Requirements

All resource management write endpoints must be admin-only.

- Require authenticated user.
- Require JWT `role` exactly equal to `"admin"`.
- Read auth from the existing `access_token` cookie first, then bearer token fallback.
- Return `401` with `action: "refresh"` for refreshable auth failures.
- Return `403 {"error":"Forbidden","code":"AUTH_FORBIDDEN"}` for non-admin users.

## Existing Endpoint To Keep

```txt
PATCH /api/v1/resources/{resourceCode}/status
```

Request:

```json
{
  "status": "maintenance"
}
```

Allowed values:

- `"active"`
- `"inactive"`
- `"maintenance"`

This endpoint is enough for the current status dropdown.

## New Endpoint Needed

Add a general partial update endpoint for editable resource fields:

```txt
PATCH /api/v1/resources/{resourceCode}
```

This endpoint should update one or more fields on an existing resource. It should not require the frontend to resend the full resource object.

Request type:

```ts
type ResourceStatus = "active" | "inactive" | "maintenance";

type ResourceLocationPatch = {
  site?: string;
  building?: string;
  floor?: string;
  room?: string;
  timezone?: string;
};

type UpdateResourcePayload = {
  name?: string;
  type?: string;
  status?: ResourceStatus;
  location?: ResourceLocationPatch;
  slotDurationMin?: number;
  defaultCapacity?: number;
  tags?: string[];
  metadata?: Record<string, unknown>;
};
```

Example request to update capacity only:

```json
{
  "defaultCapacity": 4
}
```

Example request to update room detail and capacity:

```json
{
  "name": "Room A102",
  "location": {
    "room": "A102"
  },
  "defaultCapacity": 3
}
```

Example request to update slot duration:

```json
{
  "slotDurationMin": 45
}
```

Example success response:

```json
{
  "message": "Resource updated",
  "item": {
    "resourceCode": "ROOM_A102",
    "name": "Room A102",
    "type": "clinic",
    "status": "active",
    "location": {
      "site": "NUS",
      "building": "University Health Centre",
      "floor": "",
      "room": "A102",
      "timezone": "Asia/Singapore"
    },
    "slotDurationMin": 30,
    "defaultCapacity": 3,
    "tags": ["room", "clinic"],
    "metadata": {
      "source": "admin-room-form"
    }
  }
}
```

## Validation Rules

Use the same field names as create.

- Do not allow updating `resourceCode` through this endpoint.
- If `name` is provided, it must be a non-empty string.
- If `type` is provided, it must be a non-empty string.
- If `status` is provided, it must be `"active"`, `"inactive"`, or `"maintenance"`.
- If `slotDurationMin` is provided, it must be a number and at least `5`.
- If `defaultCapacity` is provided, it must be a number and at least `1`.
- If `location` is provided, it must be an object, not `null`.
- If any nested `location` field is provided, it must be a string, not `null`.
- If `tags` is provided, it must be an array of strings.
- If `metadata` is provided, it must be an object, not `null`, a string, or an array.

For partial updates, omitted fields should keep their existing values.

## Error Responses

Return JSON errors with the same style as the current resource service.

Validation failure:

```json
{
  "error": "Invalid request payload: defaultCapacity: Input should be greater than or equal to 1",
  "details": [
    {
      "loc": ["defaultCapacity"],
      "message": "Input should be greater than or equal to 1",
      "type": "greater_than_equal"
    }
  ]
}
```

Resource not found:

```json
{
  "error": "Resource not found",
  "code": "RESOURCE_NOT_FOUND"
}
```

Forbidden:

```json
{
  "error": "Forbidden",
  "code": "AUTH_FORBIDDEN"
}
```

## Frontend Usage Target

Once `PATCH /api/v1/resources/{resourceCode}` exists, the frontend can support editing existing room capacity with:

```ts
await resourceFetch(`/api/v1/resources/${encodeURIComponent(resourceCode)}`, {
  method: "PATCH",
  headers: {
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    defaultCapacity: Number(capacityInput),
  }),
});
```

The current frontend can already create capacity because `POST /api/v1/resources` accepts `defaultCapacity`.

## Acceptance Checklist

- `PATCH /api/v1/resources/{resourceCode}` is admin-only.
- Partial updates preserve omitted fields.
- `defaultCapacity` can be updated without changing any other field.
- `slotDurationMin` can be updated without changing any other field.
- `location.room` can be updated without replacing the full location object with missing defaults.
- `resourceCode` cannot be changed by this endpoint.
- Validation errors include top-level `error` and field-level `details`.
- `404 RESOURCE_NOT_FOUND` is returned for missing resources.
- Existing `PATCH /api/v1/resources/{resourceCode}/status` keeps working.
