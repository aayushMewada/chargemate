# ChargeMate

ChargeMate is a backend-first EV charging platform for discovering charging
stations, reserving time slots, collecting payments, and recording charging
sessions. It is designed to demonstrate production-oriented backend concepts
such as geospatial search, transactional concurrency control, token rotation,
idempotent payments, caching, background jobs, and containerized deployment.

The interactive map frontend will be added after the backend API is complete.
It will use OpenStreetMap data with Leaflet or MapLibre, avoiding a paid map
API for normal map rendering.

## Main capabilities

- Secure registration and login with password hashing and account lockout
- Short-lived JWT access tokens and rotating opaque refresh tokens
- Refresh-token reuse detection, per-session logout, and logout from all devices
- Role-based authorization for users, station administrators, and system admins
- PostgreSQL/PostGIS station storage and indexed radius searches
- Open Charge Map integration for non-bookable public charging locations
- Redis caching and rate limiting
- Concurrency-safe booking holds that prevent overlapping reservations
- Optimistic concurrency control for bookings, stations, and charge points
- Razorpay order creation, checkout verification, signed webhooks, and refunds
- Idempotent webhook and payment processing
- Metered charging-session start and completion
- RQ background jobs for expiring holds and reconciling refunds
- Docker-based production topology and GitHub Actions CI

## Technology

- Python 3.12 and Flask
- SQLAlchemy, Alembic, PostgreSQL 17, and PostGIS
- Redis and RQ
- Pydantic request validation
- PyJWT access tokens and database-backed refresh sessions
- Razorpay and Open Charge Map
- Gunicorn and Docker Compose
- Pytest

## Architecture

The Flask routes validate HTTP input and translate application results into
JSON responses. Service modules contain business rules and transaction
boundaries. SQLAlchemy models describe persistent state, while PostgreSQL is
the source of truth. Redis is used only for temporary data such as cached
searches, rate-limit counters, and job queues.

Production-style Docker Compose runs five services:

- `postgres`: durable relational and geospatial data
- `redis`: cache, rate limits, and RQ queue storage
- `migrate`: applies Alembic migrations and exits successfully
- `api`: serves Flask through Gunicorn
- `worker`: processes maintenance jobs from Redis

## Local setup on Windows

Prerequisites: Python 3.12, Git, Docker Desktop, and PowerShell.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Replace the placeholder secrets in `.env`. The real `.env` file is ignored by
Git and must never be committed. Start PostgreSQL and Redis for development:

```powershell
docker compose up -d postgres redis
python -m flask --app chargemate:create_app db upgrade
python -m flask --app chargemate:create_app run
```

The development API is available at `http://127.0.0.1:5000`.

## Production-style containers

Build and start the complete stack:

```powershell
docker compose up --build -d
docker compose ps -a
```

The `migrate` service should exit with code `0`; the API, worker, PostgreSQL,
and Redis services should remain running. Check readiness with:

```powershell
Invoke-RestMethod http://127.0.0.1:5000/health/ready
```

Enqueue one run of the maintenance jobs:

```powershell
docker compose exec api `
    python -m flask --app chargemate:create_app maintenance enqueue
```

In deployment, a scheduler or cron service should invoke this command at the
desired interval. The RQ worker consumes the jobs continuously.

## API overview

The complete machine-readable contract is in
[`docs/openapi.yaml`](docs/openapi.yaml).

| Area | Important endpoints |
| --- | --- |
| Health | `GET /health`, `GET /health/ready` |
| Authentication | `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`, `GET /auth/me`, `POST /auth/logout` |
| Stations | `GET /stations`, `GET /stations/external`, `POST /stations`, `PATCH /stations/{id}` |
| Bookings | `POST /bookings`, `GET /bookings/me`, `POST /bookings/{id}/cancel` |
| Payments | `POST /payments/orders`, `POST /payments/verify`, `POST /payments/webhooks/razorpay` |
| Charging sessions | `POST /charging-sessions`, `POST /charging-sessions/{id}/complete`, `GET /charging-sessions/me` |

Protected endpoints accept an access token through:

```text
Authorization: Bearer <access-token>
```

The refresh token is not returned to browser JavaScript. It is stored in an
HTTP-only cookie scoped to `/auth` and rotated whenever `/auth/refresh` is
called.

## Concurrency and consistency

ChargeMate uses different protections for different race conditions:

- A PostgreSQL exclusion constraint prevents overlapping active bookings for
  the same charge point.
- Transactions and row locks protect critical booking and payment transitions.
- Integer `version` fields prevent lost updates through optimistic concurrency.
- Idempotency keys prevent duplicate payment orders.
- Unique webhook event IDs make repeated provider callbacks safe.
- Redis improves performance but never decides whether a booking or payment is
  valid; PostgreSQL remains authoritative.

## Tests

Run the complete test suite from the activated virtual environment:

```powershell
python -m pytest -q
```

GitHub Actions repeats the tests, applies all migrations to PostGIS, and builds
the production Docker image for pushes to `main` and pull requests.

## Configuration

The environment variable names are documented in `.env.example`:

- `SECRET_KEY` and `JWT_SECRET_KEY`
- `DATABASE_URL` and `REDIS_URL`
- `OPEN_CHARGE_MAP_API_KEY`
- `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, and `RAZORPAY_WEBHOOK_SECRET`

Use test-mode Razorpay credentials during development. Never expose provider
secrets or the JWT secret to the future frontend.
