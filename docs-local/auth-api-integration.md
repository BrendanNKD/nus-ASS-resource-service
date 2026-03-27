# Auth Service API Documentation (Frontend Integration)

This document describes the HTTP contract exposed by the Go auth service for frontend integration.

## 1) Service Overview

- Service purpose: user registration, login, token refresh, logout, health, and JWKS publishing.
- API version prefix: `/api/v1`
- Default local base URL: `http://localhost:8080`
- Content type: JSON for request/response payloads unless otherwise noted.
- Route auth requirement: all routes listed here are public endpoints.

Available routes:

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `GET /api/v1/.well-known/jwks.json`
- `GET /api/v1/health`

## 2) Authentication Model

The service uses short-lived access tokens + long-lived refresh tokens.

Access token:

- JWT signed with `RS256`
- Returned in response JSON (`access_token`)
- Also set in an `HttpOnly` cookie
- Default TTL: `15m` (`expires_in` = `900` seconds unless changed)

Refresh token:

- Opaque random token (not JWT)
- Set only in `HttpOnly` cookie
- Never returned in JSON body
- Default TTL: `720h` (30 days)
- Rotated on every successful refresh
- Reuse detection is enforced (reused/old tokens are revoked)

Access token claims:

- `username` (string)
- `role` (string)
- Standard registered claims: `iss`, `iat`, `nbf`, `exp`

## 3) Cookies

On successful `login` and `refresh`, server sets both cookies:

- Access cookie name: `AUTH_ACCESS_COOKIE_NAME` (default `access_token`)
- Refresh cookie name: `AUTH_REFRESH_COOKIE_NAME` (default `refresh_token`)
- `HttpOnly: true`
- `Path: COOKIE_PATH` (default `/`)
- `Domain: COOKIE_DOMAIN` (default empty; commonly set to `localhost` in local env)
- `Secure: COOKIE_SECURE` (default `false` in dev, `true` in prod)
- `SameSite: COOKIE_SAMESITE` (`lax`, `strict`, or `none`; default `lax`)
- `Max-Age`: based on token TTL

On `logout`, both cookies are cleared (`Max-Age=-1`, expired timestamp).

## 4) CORS + Browser Requirements

Server CORS behavior:

- Allowed origins: `CORS_ALLOWED_ORIGINS` (CSV)
- Allowed methods: `GET, POST, PUT, PATCH, DELETE, OPTIONS`
- Allowed headers: `Content-Type, Authorization, X-Requested-With`
- Credentials: allowed (`Access-Control-Allow-Credentials: true`)

Frontend requirement for cookie-based auth:

- Send requests with credentials enabled.
- `fetch(..., { credentials: "include" })`
- Axios: `{ withCredentials: true }`

Without credentials, browser will not send refresh/access cookies.

## 5) Error Response Contract

For auth/JWKS endpoints (wrapped by error middleware), errors are returned as:

```json
{
  "error": "Human-readable message"
}
```

HTTP status codes vary by endpoint (see below).

## 6) Endpoint Contracts

### POST `/api/v1/auth/register`

Creates a new user.

Request body:

```json
{
  "username": "alice",
  "password": "secret123",
  "email": "alice@example.com",
  "role": "user"
}
```

Notes:

- `username` and `password` are required.
- `email` optional.
- `role` optional; defaults to `"user"` (trimmed).
- If provided role does not exist in DB roles table, request fails.

Success response:

- `201 Created`

```json
{
  "message": "User registered successfully"
}
```

Common errors:

- `400` `{"error":"Invalid request payload"}`
- `400` `{"error":"Username and password are required"}`
- `400` `{"error":"Invalid role"}`
- `409` `{"error":"User already exists or database error"}`
- `500` `{"error":"Internal server error"}`

---

### POST `/api/v1/auth/login`

Authenticates user and issues tokens.

Request body:

```json
{
  "username": "alice",
  "password": "secret123"
}
```

Success response:

- `200 OK`

```json
{
  "message": "Login successful",
  "access_token": "<jwt>",
  "token_type": "Bearer",
  "expires_in": 900
}
```

Also returns `Set-Cookie` headers for access and refresh cookies.

Common errors:

- `400` `{"error":"Invalid request payload"}`
- `400` `{"error":"Username and password are required"}`
- `401` `{"error":"Invalid username or password"}`
- `500` `{"error":"Internal server error"}`
- `500` `{"error":"Could not generate tokens"}`

---

### POST `/api/v1/auth/refresh`

Rotates refresh token and returns a new access token.

Request body: none

Credential requirement:

- Refresh cookie must be present in request.

Success response:

- `200 OK`

```json
{
  "message": "Token refreshed",
  "access_token": "<jwt>",
  "token_type": "Bearer",
  "expires_in": 900
}
```

Also returns new access and refresh cookies (`Set-Cookie`), replacing previous values.

Common errors:

- `401` `{"error":"Refresh token is required"}` (cookie missing)
- `401` `{"error":"Refresh token revoked"}` (invalid, expired, revoked, reused, or session mismatch)
- `500` `{"error":"Could not refresh token"}`

---

### POST `/api/v1/auth/logout`

Revokes server-side refresh session when possible and clears auth cookies.

Request body: none

Success response:

- `200 OK`

```json
{
  "message": "Logged out successfully"
}
```

Notes:

- Safe to call even if token/cookie is missing or invalid.
- Response still clears both access and refresh cookies.

---

### GET `/api/v1/.well-known/jwks.json`

Returns JWKS for verifying access JWT signatures.

Success response:

- `200 OK`

```json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "auth-service-1",
      "alg": "RS256",
      "n": "<base64url modulus>",
      "e": "AQAB"
    }
  ]
}
```

Common errors:

- `500` `{"error":"Could not encode JWKS"}`

---

### GET `/api/v1/health`

Liveness endpoint.

Success response:

- `200 OK`

```json
{
  "status": "ok"
}
```

## 7) Frontend Integration Flow (Recommended)

1. Register user with `/auth/register` (optional if user already exists).
2. Login via `/auth/login` with `credentials: "include"`.
3. Keep `access_token` in memory (not localStorage if possible) for `Authorization: Bearer ...` calls to protected APIs.
4. On `401` from protected API, call `/auth/refresh` once (also with credentials).
5. If refresh succeeds, retry original request once with new `access_token`.
6. If refresh fails (`401`), treat session as logged out and route to login page.
7. Call `/auth/logout` during explicit sign-out and clear any client auth state.

## 8) Frontend Fetch Examples

Login:

```ts
const res = await fetch("http://localhost:8080/api/v1/auth/login", {
  method: "POST",
  credentials: "include",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ username, password }),
});

if (!res.ok) throw await res.json();
const data = await res.json(); // { access_token, token_type, expires_in, message }
```

Refresh:

```ts
const res = await fetch("http://localhost:8080/api/v1/auth/refresh", {
  method: "POST",
  credentials: "include",
});

if (!res.ok) throw await res.json();
const data = await res.json(); // new access_token
```

Logout:

```ts
await fetch("http://localhost:8080/api/v1/auth/logout", {
  method: "POST",
  credentials: "include",
});
```

## 9) Config Values That Affect Frontend Behavior

- `CORS_ALLOWED_ORIGINS`: frontend origins allowed by browser CORS checks.
- `COOKIE_SECURE`: must be `true` in HTTPS production deployments.
- `COOKIE_SAMESITE`: cross-site behavior (`none` requires `secure=true` in browsers).
- `COOKIE_DOMAIN` and `COOKIE_PATH`: scope of auth cookies.
- `AUTH_ACCESS_COOKIE_NAME`, `AUTH_REFRESH_COOKIE_NAME`: cookie keys expected by backend.
- `JWT_ACCESS_TTL`: reflected as `expires_in` in login/refresh responses.

## 10) Implementation Notes / Caveats

- Refresh endpoint only reads the refresh token from cookie, not request body/header.
- Login/refresh return access token in both response body and cookie.
- Error messages are stable strings and can be shown directly or mapped to UI copy.
- Role comparison in DB is case-insensitive (`CITEXT`), but role must exist in `roles` table.
