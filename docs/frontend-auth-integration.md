# Frontend Auth + Refresh Contract (Resource Service)

This resource service expects the same access-token cookie issued by `go-auth-service`.

## 1) Request Requirements

- Send cookies with every protected API request.
- Browser `fetch` must use `credentials: "include"`.
- Cookie name defaults to `access_token` (`AUTH_ACCESS_COOKIE_NAME`).

## 2) How Token Is Validated

- Service reads token from cookie first, then `Authorization: Bearer` fallback.
- Token is verified using RS256 public key from:
  - `JWT_ACCESS_PUBLIC_KEY` (or derived from `JWT_ACCESS_PRIVATE_KEY`)
- Issuer must match `JWT_ISSUER` (same as auth-service).

## 3) Unauthorized Response Format

Protected endpoints return JSON (not HTML):

```json
{
  "error": "Authentication required",
  "code": "AUTH_TOKEN_MISSING",
  "action": "refresh"
}
```

Possible `code` values:

- `AUTH_TOKEN_MISSING`
- `AUTH_TOKEN_EXPIRED`
- `AUTH_TOKEN_INVALID`
- `AUTH_FORBIDDEN` (403)

## 4) Frontend Refresh Behavior

When response is `401` and `action == "refresh"`:

1. Call auth-service refresh endpoint (`POST /api/v1/auth/refresh`) with `credentials: "include"`.
2. If refresh succeeds (`200`), retry original resource request once.
3. If refresh fails (`401`), clear local user state and redirect to login.

## 5) Example Frontend Pseudocode

```ts
async function callResource(url: string, init: RequestInit = {}) {
  const doRequest = () => fetch(url, { ...init, credentials: "include" });

  let res = await doRequest();
  if (res.status !== 401) return res;

  const body = await res.clone().json().catch(() => null);
  if (!body || body.action !== "refresh") return res;

  const refresh = await fetch("/api/v1/auth/refresh", {
    method: "POST",
    credentials: "include",
  });

  if (refresh.ok) {
    return doRequest();
  }

  // refresh failed -> send user to login
  window.location.href = "/login";
  return res;
}
```
