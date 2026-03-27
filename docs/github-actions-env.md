# GitHub Actions Variables and Secrets

This repository uses two workflows:
- `CI` (`.github/workflows/ci.yaml`)
- `CD` (`.github/workflows/cd.yaml`)

## 1) Required GitHub Secrets

### Required for CI

- `GITHUB_TOKEN` (auto-provided by GitHub Actions)
- `SNYK_TOKEN` (optional; only required if you want Snyk scan enabled)

### Required for CD

- `AWS_ROLE_ARN`
- `ECS_CLUSTER`
- `ECS_SERVICE`
- `ECS_TASK_DEFINITION`
- `ECS_CONTAINER_NAME`
- `ECS_ECR_REPOSITORY`
- `SERVICE_HEALTHCHECK_URL` (optional but recommended)

## 2) Runtime Environment Variables (Container/App)

These are needed in ECS task definition (or your runtime platform), not as workflow vars.

### Core service

- `APP_ENV` (`dev` or `prod`)
- `APP_PORT` (default `8080`)
- `CORS_ALLOWED_ORIGINS`
- `AUTH_ACCESS_COOKIE_NAME` (default `access_token`)
- `JWT_ISSUER` (must match auth-service issuer)

### JWT key material

In `APP_ENV=prod`, these are loaded from AWS Secrets Manager secret `prod/jwt`.

- `JWT_ACCESS_PRIVATE_KEY`
- `JWT_ACCESS_PUBLIC_KEY`
- `JWT_ACCESS_KID`

### Database (MongoDB)

Resource service is MongoDB-backed.

In `APP_ENV=prod`, these are loaded from secret name `prod/postgres` (legacy name retained by request):

- `DB_ENGINE` (set to `mongodb`)
- `DB_NAME` / `MONGODB_DBNAME`
- `DB_HOST` / `MONGODB_HOST`
- `DB_PORT` / `MONGODB_PORT`
- `DB_USERNAME` / `MONGODB_USERNAME`
- `DB_PASSWORD` / `MONGODB_PASSWORD`
- `MONGODB_URI` (optional, if you prefer full URI)
- `MONGODB_TLS` (optional)

### Valkey

In `APP_ENV=prod`, these are loaded from secret `prod/valkey`.

- `VALKEY_ADDR`
- `VALKEY_PASSWORD`
- `VALKEY_DB`
- `VALKEY_PREFIX`
- `VALKEY_USE_TLS`

## 3) Secret JSON Shapes

### `prod/jwt`

```json
{
  "JWT_ACCESS_PRIVATE_KEY": "-----BEGIN PRIVATE KEY-----\\n...\\n-----END PRIVATE KEY-----",
  "JWT_ACCESS_PUBLIC_KEY": "-----BEGIN PUBLIC KEY-----\\n...\\n-----END PUBLIC KEY-----",
  "JWT_ACCESS_KID": "auth-service-1",
  "JWT_ISSUER": "auth-service"
}
```

### `prod/postgres` (legacy name, Mongo payload)

```json
{
  "engine": "mongodb",
  "host": "your-mongo-host",
  "port": 27017,
  "dbname": "resource_db",
  "username": "resource_user",
  "password": "resource_password",
  "uri": ""
}
```

### `prod/valkey`

```json
{
  "VALKEY_ADDR": "your-valkey-endpoint:6379",
  "VALKEY_PASSWORD": "",
  "VALKEY_DB": "0",
  "VALKEY_PREFIX": "resource:cache",
  "VALKEY_USE_TLS": "true"
}
```
