# Frontend Resource Service Integration

This document is the implementation handoff for integrating the frontend with `nus-ASS-resource-service`.

Assumption: auth login is already integrated through `go-auth-service`, and the browser already receives the `HttpOnly` auth cookies.

## Services

Use separate configurable base URLs:

```ts
const AUTH_API_BASE_URL = process.env.NEXT_PUBLIC_AUTH_API_BASE_URL ?? "http://localhost:8080";
const RESOURCE_API_BASE_URL = process.env.NEXT_PUBLIC_RESOURCE_API_BASE_URL ?? "http://localhost:8081";
```

Notes:

- Auth service default local port is usually `8080`.
- Resource service may run on `8081` locally when both services run together, even though its `APP_PORT` default is `8080`.
- Do not hard-code these URLs in components. Keep them in the frontend environment/config layer.

## Auth Model For Resource Calls

The resource service accepts the same access JWT issued by `go-auth-service`.

- Cookie name defaults to `access_token`.
- Cookie is `HttpOnly`, so frontend JavaScript should not try to read it.
- The resource service reads the access token from cookie first, then falls back to `Authorization: Bearer <token>`.
- For browser integration, use cookie auth and send every protected request with credentials:

```ts
fetch(url, {
  credentials: "include",
});
```

The frontend origin must be in `CORS_ALLOWED_ORIGINS` for both auth service and resource service. Credentialed CORS requests cannot use wildcard origins.

## Auth Health Check

Before debugging resource create, verify that the resource service can see the auth cookie:

```ts
const res = await fetch(`${RESOURCE_API_BASE_URL}/api/v1/auth/context`, {
  method: "GET",
  credentials: "include",
});

const body = await res.json();
```

Expected success response:

```json
{
  "message": "Authenticated",
  "user": {
    "username": "admin",
    "role": "admin"
  }
}
```

If this returns:

- `401`: the resource request did not include a valid access cookie, or the cookie is expired/invalid.
- `403` on create only: the user is authenticated but the JWT `role` is not exactly `"admin"`.

## Shared Request Helper

Integrate resource calls through the existing authenticated API client if one already exists. The important pieces are `credentials: "include"`, JSON headers for JSON bodies, and one refresh/retry when the resource service returns a refreshable `401`.

```ts
type ApiError = {
  error?: string;
  code?: string;
  action?: string;
};

async function parseJsonSafe<T>(res: Response): Promise<T | null> {
  return res
    .clone()
    .json()
    .catch(() => null);
}

async function refreshAccessToken(): Promise<boolean> {
  const refresh = await fetch(`${AUTH_API_BASE_URL}/api/v1/auth/refresh`, {
    method: "POST",
    credentials: "include",
  });

  return refresh.ok;
}

export async function resourceFetch(path: string, init: RequestInit = {}, retry = true) {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(`${RESOURCE_API_BASE_URL}${path}`, {
    ...init,
    headers,
    credentials: "include",
  });

  if (res.status !== 401 || !retry) {
    return res;
  }

  const body = await parseJsonSafe<ApiError>(res);
  if (body?.action !== "refresh") {
    return res;
  }

  const refreshed = await refreshAccessToken();
  if (!refreshed) {
    return res;
  }

  return resourceFetch(path, init, false);
}
```

## Resource Types

Use the backend field names exactly as shown here for frontend payloads and responses.

```ts
export type ResourceStatus = "active" | "inactive" | "maintenance";

export type ResourceLocation = {
  site?: string;
  building?: string;
  floor?: string;
  room?: string;
  timezone?: string;
};

export type Resource = {
  resourceCode: string;
  name: string;
  type: string;
  status: ResourceStatus;
  location: {
    site: string;
    building: string;
    floor: string;
    room: string;
    timezone: string;
  };
  slotDurationMin: number;
  // UI label: Capacity. This is how many people/bookings can fit in a slot by default.
  defaultCapacity: number;
  tags: string[];
  metadata: Record<string, unknown>;
};

export type CreateResourcePayload = {
  resourceCode: string;
  name: string;
  type: string;
  status?: ResourceStatus;
  location?: ResourceLocation;
  slotDurationMin?: number;
  // UI label: Capacity. Send as defaultCapacity, not capacity.
  defaultCapacity?: number;
  tags?: string[];
  metadata?: Record<string, unknown>;
};
```

Backend defaults when fields are omitted:

- `status`: `"active"`
- `location`: `{ "site": "", "building": "", "floor": "", "room": "", "timezone": "UTC" }`
- `slotDurationMin`: `30`
- `defaultCapacity`: `1`
- `tags`: `[]`
- `metadata`: `{}`

Frontend naming note:

- The form can label this field as `Capacity`.
- The API field name must be `defaultCapacity`.
- `defaultCapacity` means the default number of people/bookings that can use the resource in one time slot.
- Do not send `capacity`; the current resource service contract expects `defaultCapacity`.

## Create Resource

Endpoint:

```txt
POST /api/v1/resources
```

The request body must be a JSON object. The backend error below means the frontend did not send a JSON object:

```txt
Invalid request payload: Input should be a valid dictionary or instance of ResourceCreateRequest
```

Most common causes:

- `body` is missing or `undefined`.
- `body` is `JSON.stringify(JSON.stringify(payload))` instead of `JSON.stringify(payload)`.
- `body` is a plain string such as `"CLINIC_A"`.
- `body` is `null`.
- `body` is `FormData`.
- The payload is nested under another key, for example `{ "payload": { ... } }` or `{ "resource": { ... } }`.
- The request is missing `Content-Type: application/json`.

Auth:

- Requires authenticated user.
- Requires JWT role exactly equal to `"admin"`.

Minimum valid request:

```json
{
  "resourceCode": "CLINIC_A",
  "name": "Clinic A",
  "type": "clinic",
  "defaultCapacity": 2
}
```

Exact browser request:

```ts
const payload = {
  resourceCode: "CLINIC_A",
  name: "Clinic A",
  type: "clinic",
  defaultCapacity: 2,
};

const res = await fetch(`${RESOURCE_API_BASE_URL}/api/v1/resources`, {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
  },
  body: JSON.stringify(payload),
});
```

Do not send:

```ts
// Wrong: double-stringified, backend receives a string.
body: JSON.stringify(JSON.stringify(payload));

// Wrong: nested object, backend cannot find resourceCode/name/type at top level.
body: JSON.stringify({ resource: payload });

// Wrong: no JSON object body.
body: undefined;

// Wrong: FormData is not this endpoint's contract.
body: formData;
```

Full valid request:

```json
{
  "resourceCode": "CLINIC_A",
  "name": "Clinic A",
  "type": "clinic",
  "status": "active",
  "location": {
    "site": "NUS",
    "building": "University Health Centre",
    "floor": "1",
    "room": "A101",
    "timezone": "Asia/Singapore"
  },
  "slotDurationMin": 30,
  "defaultCapacity": 2,
  "tags": ["clinic", "health"],
  "metadata": {
    "notes": "General consultation room"
  }
}
```

Frontend implementation:

```ts
export async function createResource(payload: CreateResourcePayload): Promise<Resource> {
  const res = await resourceFetch("/api/v1/resources", {
    method: "POST",
    body: JSON.stringify(payload),
  });

  const body = await parseJsonSafe<{
    message?: string;
    item?: Resource;
    error?: string;
    code?: string;
  }>(res);

  if (!res.ok) {
    throw new Error(body?.error ?? `Create resource failed with HTTP ${res.status}`);
  }

  if (!body?.item) {
    throw new Error("Create resource succeeded but response item was missing");
  }

  return body.item;
}
```

Success response:

```json
{
  "message": "Resource created",
  "item": {
    "resourceCode": "CLINIC_A",
    "name": "Clinic A",
    "type": "clinic",
    "status": "active",
    "location": {
      "site": "NUS",
      "building": "University Health Centre",
      "floor": "1",
      "room": "A101",
      "timezone": "Asia/Singapore"
    },
    "slotDurationMin": 30,
    "defaultCapacity": 2,
    "tags": ["clinic", "health"],
    "metadata": {
      "notes": "General consultation room"
    }
  }
}
```

## Avoiding The Current 400 On Create

The resource service returns `400` when request validation fails:

```json
{
  "error": "Invalid request payload: resourceCode: String should have at least 1 character",
  "details": [
    {
      "loc": ["resourceCode"],
      "message": "String should have at least 1 character",
      "type": "string_too_short"
    }
  ]
}
```

Use the top-level `error` for a quick banner message, and use `details[*].loc` to map the backend validation error back to a form field.

Common frontend causes:

- Request body is nested incorrectly, for example `{ "resource": { ... } }` instead of sending the payload object directly.
- Missing required fields: `resourceCode`, `name`, or `type`.
- Required string fields are empty strings: `resourceCode: ""`, `name: ""`, or `type: ""`.
- `status` is not one of `"active"`, `"inactive"`, or `"maintenance"`. Values like `"Active"`, `"ACTIVE"`, `"disabled"`, or `"available"` will fail.
- `slotDurationMin` is provided but is less than `5`, `null`, or an empty string.
- `defaultCapacity` is provided but is less than `1`, `null`, or an empty string.
- `location` is sent as `null`. Omit it or send an object.
- Any `location` field is sent as `null`. Use an empty string/default or omit that nested field.
- `tags` is not an array of strings.
- `metadata` is not an object, for example `null`, a string, or an array.
- The request is not sent as JSON with `Content-Type: application/json`.

Recommended form normalization before submit:

```ts
function optionalNumber(value: string, fallback: number): number {
  const trimmed = value.trim();
  if (!trimmed) return fallback;
  return Number(trimmed);
}

export function buildCreateResourcePayload(form: {
  resourceCode: string;
  name: string;
  type: string;
  status?: string;
  site?: string;
  building?: string;
  floor?: string;
  room?: string;
  timezone?: string;
  slotDurationMin?: string;
  defaultCapacity?: string;
  tagsCsv?: string;
  metadata?: Record<string, unknown>;
}): CreateResourcePayload {
  return {
    resourceCode: form.resourceCode.trim(),
    name: form.name.trim(),
    type: form.type.trim(),
    status: (form.status || "active") as ResourceStatus,
    location: {
      site: form.site?.trim() ?? "",
      building: form.building?.trim() ?? "",
      floor: form.floor?.trim() ?? "",
      room: form.room?.trim() ?? "",
      timezone: form.timezone?.trim() || "Asia/Singapore",
    },
    slotDurationMin: optionalNumber(form.slotDurationMin ?? "", 30),
    defaultCapacity: optionalNumber(form.defaultCapacity ?? "", 1),
    tags: (form.tagsCsv ?? "")
      .split(",")
      .map((tag) => tag.trim())
      .filter(Boolean),
    metadata: form.metadata ?? {},
  };
}
```

Also add client-side checks before calling the API:

```ts
function validateCreateResourcePayload(payload: CreateResourcePayload) {
  if (!payload.resourceCode.trim()) return "Resource code is required";
  if (!payload.name.trim()) return "Name is required";
  if (!payload.type.trim()) return "Type is required";
  if (payload.status && !["active", "inactive", "maintenance"].includes(payload.status)) {
    return "Invalid status";
  }
  if (payload.slotDurationMin !== undefined && payload.slotDurationMin < 5) {
    return "Slot duration must be at least 5 minutes";
  }
  if (payload.defaultCapacity !== undefined && payload.defaultCapacity < 1) {
    return "Default capacity must be at least 1";
  }
  if (payload.slotDurationMin !== undefined && Number.isNaN(payload.slotDurationMin)) {
    return "Slot duration must be a number";
  }
  if (payload.defaultCapacity !== undefined && Number.isNaN(payload.defaultCapacity)) {
    return "Default capacity must be a number";
  }
  return null;
}
```

## List Resources

Endpoint:

```txt
GET /api/v1/resources
GET /api/v1/resources?status=active
GET /api/v1/resources?type=clinic
GET /api/v1/resources?status=active&type=clinic
```

Auth:

- Requires authenticated user.
- Does not require admin role.

Frontend implementation:

```ts
export async function listResources(params?: {
  status?: ResourceStatus;
  type?: string;
}): Promise<Resource[]> {
  const query = new URLSearchParams();
  if (params?.status) query.set("status", params.status);
  if (params?.type) query.set("type", params.type);

  const suffix = query.toString() ? `?${query.toString()}` : "";
  const res = await resourceFetch(`/api/v1/resources${suffix}`, {
    method: "GET",
  });

  const body = await parseJsonSafe<{
    message?: string;
    requested_by?: string;
    items?: Resource[];
    error?: string;
  }>(res);

  if (!res.ok) {
    throw new Error(body?.error ?? `List resources failed with HTTP ${res.status}`);
  }

  return body?.items ?? [];
}
```

Success response:

```json
{
  "message": "Resources fetched",
  "requested_by": "alice",
  "items": []
}
```

## Patch Resource Status

Endpoint:

```txt
PATCH /api/v1/resources/{resourceCode}/status
```

Auth:

- Requires authenticated user.
- Requires JWT role exactly equal to `"admin"`.

Request:

```json
{
  "status": "maintenance"
}
```

Frontend implementation:

```ts
export async function updateResourceStatus(
  resourceCode: string,
  status: ResourceStatus,
): Promise<Resource> {
  const res = await resourceFetch(
    `/api/v1/resources/${encodeURIComponent(resourceCode)}/status`,
    {
      method: "PATCH",
      body: JSON.stringify({ status }),
    },
  );

  const body = await parseJsonSafe<{
    message?: string;
    item?: Resource;
    error?: string;
    code?: string;
  }>(res);

  if (!res.ok) {
    throw new Error(body?.error ?? `Update resource status failed with HTTP ${res.status}`);
  }

  if (!body?.item) {
    throw new Error("Update resource status succeeded but response item was missing");
  }

  return body.item;
}
```

Possible failures:

- `400 {"error":"Invalid request payload","details":[...]}` if status is not one of the allowed values.
- `401 {"error":"Access token expired","code":"AUTH_TOKEN_EXPIRED","action":"refresh"}` if the access cookie expired.
- `403 {"error":"Forbidden","code":"AUTH_FORBIDDEN"}` if the user is not admin.
- `404 {"error":"Resource not found","code":"RESOURCE_NOT_FOUND"}` if `resourceCode` does not exist.

## Error Handling Matrix

Resource service errors:

| Status | Body | Frontend action |
| --- | --- | --- |
| `400` | `{"error":"Invalid request payload: ...","details":[...]}` | Fix request payload or show validation error. Do not refresh. |
| `401` | `{"error":"Authentication required","code":"AUTH_TOKEN_MISSING","action":"refresh"}` | Call auth refresh once, then retry original request once. |
| `401` | `{"error":"Access token expired","code":"AUTH_TOKEN_EXPIRED","action":"refresh"}` | Call auth refresh once, then retry original request once. |
| `401` | `{"error":"Invalid access token","code":"AUTH_TOKEN_INVALID","action":"refresh"}` | Call auth refresh once. If refresh fails, route to login. |
| `403` | `{"error":"Forbidden","code":"AUTH_FORBIDDEN"}` | Show not-authorized/admin-required state. Do not refresh. |
| `404` | `{"error":"Resource not found","code":"RESOURCE_NOT_FOUND"}` | Show not-found state. |
| `409` | `{"error":"Resource already exists","code":"RESOURCE_CONFLICT"}` | Show duplicate resource code validation. |

Auth service refresh failures are simpler and return `{"error":"..."}`. If `POST /api/v1/auth/refresh` returns `401`, treat the user as logged out.

## Frontend Acceptance Checklist

- All resource requests use `credentials: "include"`.
- `POST /api/v1/resources` sends the payload object directly, not nested.
- Create payload uses `resourceCode`, `slotDurationMin`, and `defaultCapacity`.
- Create form normalizes empty numeric inputs to omitted/default numeric values, not empty strings or `null`.
- Create form restricts status to `"active"`, `"inactive"`, or `"maintenance"`.
- Admin screens verify `/api/v1/auth/context` and handle non-admin users.
- `401` with `action: "refresh"` triggers exactly one refresh/retry cycle.
- `400` and `403` do not trigger refresh loops.
- `409 RESOURCE_CONFLICT` is shown as duplicate resource code.
- API base URLs are environment-driven.
