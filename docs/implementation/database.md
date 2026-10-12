# Database (PostgreSQL)

FORGE uses PostgreSQL through SQLAlchemy 2 (psycopg 3 driver) with Alembic migrations.
Only standard PostgreSQL features are used (UUID with `gen_random_uuid()`, JSONB, CHECK
constraints), so any PostgreSQL ≥ 13 works: local Docker, Neon, Supabase, or self-hosted.

The web app starts **without** a database. `/` and `/health` never touch it; `/ready` reports
its state. Features that persist data (benchmark runs, from increment 6) require it.

## Local development (Docker)

```bash
docker compose up -d db
```

- Image `postgres:17`, data in the named volume `forge_pgdata` (survives restarts and
  `docker compose down`; removed only by `docker compose down -v`).
- Published on **`127.0.0.1:5433`** only (not on the network). 5433 avoids a natively
  installed PostgreSQL on 5432; change with `POSTGRES_PORT`.
- Credentials: `POSTGRES_USER`/`POSTGRES_DB` default to `forge`; `POSTGRES_PASSWORD`
  defaults to `forge-local-dev-only`. Set your own in `.env`. Never reuse these values for
  any non-local database.

Then point the app at it and apply migrations:

```bash
export DATABASE_URL=postgresql://forge:forge-local-dev-only@127.0.0.1:5433/forge
alembic upgrade head
alembic current          # shows "0001 (head)"
```

Inside Compose, the `forge` service gets `DATABASE_URL=…@db:5432/…` automatically; run
migrations there with `docker compose run --rm forge alembic upgrade head`.

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | unset | `postgres://`, `postgresql://` or `postgresql+psycopg://` — all use psycopg 3. Other schemes (SQLite, MySQL, asyncpg) are rejected. URL-encode special characters in the password. |
| `DATABASE_SSLMODE` | unset | Overrides `sslmode` in the URL. Use `require` (or `verify-full`) for hosted databases. |
| `DATABASE_POOL_MODE` | `session` | `transaction` disables server-side prepared statements, required behind PgBouncer/Supavisor in transaction mode. |
| `DATABASE_POOL_SIZE` / `DATABASE_MAX_OVERFLOW` | 5 / 5 | Per process. With Gunicorn, connections ≤ workers × (size + overflow); keep within the provider's connection limit. |
| `DATABASE_POOL_TIMEOUT` | 10 s | Wait for a free pooled connection. |
| `DATABASE_CONNECT_TIMEOUT` | 5 s | TCP/auth timeout; bounds how long `/ready` can take when the database is down. |

Connections use `pool_pre_ping` and are recycled after 300 s. Invalid values fail at startup
with a `ConfigurationError` that never contains the URL or password; logs and `repr` show
the URL with the password masked.

## Hosted PostgreSQL (not yet connected)

No hosted database has been connected or tested. The endpoint details below reflect the
providers' documentation as known when this was written; verify them in the current docs.
When you are ready:

- **Neon** (primary choice, ADR-003): copy the connection string from the Neon console.
  The pooled endpoint has `-pooler` in the hostname; with it set
  `DATABASE_POOL_MODE=transaction`. Set `DATABASE_SSLMODE=require`.
- **Supabase**: use the direct connection (port 5432, `DATABASE_POOL_MODE=session`) for
  long-running servers, or the Supavisor transaction pooler (port 6543,
  `DATABASE_POOL_MODE=transaction`). Set `DATABASE_SSLMODE=require`.
- Run migrations from a trusted machine: `DATABASE_URL=… alembic upgrade head`.

Check the providers' current documentation for quotas, connection limits and pricing; they
change and are deliberately not copied here.

## Migrations

- Location: `src/forge/db/migrations` (shipped inside the package). `alembic.ini` at the
  repository root is for the CLI and contains no URL; `env.py` reads `DATABASE_URL`.
- Never run automatically on web start. Deployment order: migrate, then roll out code.
- `alembic check` verifies that models and migrations agree. It ignores CHECK constraints,
  so `tests/db/test_migrations.py` also compares the migrated catalog with the models.
- Names in migrations are wrapped in `op.f()`; without it the metadata naming convention is
  applied twice (see "Known issue" below).
- `downgrade` drops tables and their data. Use it only on disposable databases.
- Concurrent `alembic upgrade` runs are not coordinated; run migrations from one place.

### Resolved: local databases migrated with the first draft of 0001

During increment 4 the local Compose database was migrated once with a draft of revision
`0001` whose CHECK constraint names had a doubled prefix (e.g.
`ck_executions_ck_executions_role_valid`). The draft was never committed. Behaviour is the
same; only names differ. That database held no rows and was reset with the owner's
authorization on 2026-10-12 (all 23 names now match; see phase-0-plan §7). Any other
database migrated with that draft can be fixed the same way (resets it — only after
confirming it holds nothing you need):

```bash
alembic downgrade base && alembic upgrade head
```

## Schema (revision 0001)

| Table | Holds | Deletion |
|---|---|---|
| `workspaces` | Isolation boundary; `slug` unique, lowercase format checked | `RESTRICT` while runs exist |
| `runs` | Manifest (JSONB) + SHA-256 `manifest_hash`, status, FORGE version, budget limits, timestamps | `RESTRICT` while executions exist |
| `executions` | One model call: case, system, role, sample index, provider/models, params, request hash, **raw output**, finish reason, provider-reported usage + source, latency, cache hit, error category | `RESTRICT` while evaluations exist |
| `evaluations` | Derived results from one evaluator version (results JSONB, `passed` nullable = undecidable) | — |

History is never cascade-deleted. A privacy deletion path (removing user content while
keeping anonymised aggregates) is not implemented yet.

## Tests

PostgreSQL tests (`tests/db`, marker `postgres`) need `TEST_DATABASE_URL`, e.g.
`postgresql://forge:forge-local-dev-only@127.0.0.1:5433/postgres`. Each test creates and drops
its own `forge_test_<random>` database; nothing else on the server is touched. The guard in
`tests/db/safety.py` refuses, before connecting, non-local hosts and **port 5432** (the
default port, usually a developer's own PostgreSQL; a URL without a port counts as 5432),
and, after a read-only connection, any server holding databases other than `postgres`,
`template0/1`, `forge` and `forge_test_*`. Overrides exist only for disposable servers:
`FORGE_ALLOW_REMOTE_TEST_DB=1`, `FORGE_ALLOW_TEST_DB_PORT_5432=1`. Without the variable the
tests skip with a reason; CI sets `FORGE_REQUIRE_DB_TESTS=1` so they cannot be skipped there
(its PostgreSQL service is published on 5433 for the same reason).

## Backups

Not automated. Local: `docker compose exec db pg_dump -U forge forge > forge.sql`. Hosted:
use the provider's backup/branching features.
