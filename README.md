# NUS ASS Resource Service

Python/FastAPI resource service that validates auth cookies using the same JWT key material as `go-auth-service`.

## Key Behaviors

- Access token is read from cookie (`AUTH_ACCESS_COOKIE_NAME`, default `access_token`) or `Authorization: Bearer`, but protected requests must also include the refresh cookie.
- Refresh session is checked in Valkey from the refresh cookie (`AUTH_REFRESH_COOKIE_NAME`, default `refresh_token`) before JWT verification.
- Valkey refresh-session keys use `VALKEY_PREFIX` (default `auth:refresh`) and the auth-service key format.
- JWT is verified with RS256 using `JWT_ACCESS_PUBLIC_KEY` (or public key derived from `JWT_ACCESS_PRIVATE_KEY`).
- In `APP_ENV=prod`, secrets are loaded from AWS Secrets Manager:
  - `prod/jwt`
  - `prod/postgres` (legacy secret name used for database config)
  - `prod/valkey`
- Valkey and MongoDB connections are strict in prod and warning-only in local/dev.
- Unauthorized responses are frontend-friendly JSON with refresh guidance.

## Run Locally

```bash
python -m venv .venv
source .venv/bin/activate
.\.venv\Scripts\Activate.ps1
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
pip install -e '.[dev]'
cp example.env .env
uvicorn app.main:app --reload --port 8081
```

## Test

```bash
pytest
```

## API

- `GET /api/v1/health`
- `GET /api/v1/resources` (auth required)
- `POST /api/v1/resources` (admin)
- `PATCH /api/v1/resources/{resource_code}/status` (admin)
- `GET /api/v1/auth/context` (auth required)



podman run -d `
  --name resource-mongodb `
  -p 27017:27017 `
  -e MONGODB_ROOT_PASSWORD=root_pw `
  -e MONGODB_USERNAME=app `
  -e MONGODB_PASSWORD=app_pw `
  -e MONGODB_DATABASE=resource_db `
  -v mongodb-data:/bitnami/mongodb `
  docker.io/bitnami/mongodb:latest
