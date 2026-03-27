# NUS ASS Resource Service

Python/FastAPI resource service that validates auth cookies using the same JWT key material as `go-auth-service`.

## Key Behaviors

- Access token is read from cookie (`AUTH_ACCESS_COOKIE_NAME`, default `access_token`) or `Authorization: Bearer`.
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
