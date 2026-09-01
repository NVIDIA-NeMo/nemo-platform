<!--
SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# nemo-scaled-evals (Phase 1 ephemeral plugin)

Vendors the scaled-evals control plane into NeMo Platform as an ephemeral plugin so Harbor/Gym scaled evaluation keeps working end-to-end while substrate plugins (builder/registry/sandbox) and the nemo-evaluator API merge land later.

## Install (ephemeral — not in `enabled-plugins` yet)

```bash
# From nemo-platform repo root
uv sync
uv pip install -e plugins/_temporary-scaled-evals/
```

Restart `nemo services run` after install.

## Required configuration

| Variable | Notes |
|---|---|
| `SCALED_EVALS_DATABASE_URL` | scaled-evals' own Postgres. **Not** `DATABASE_URL` — the platform injects that into the same process, and reusing it would run these migrations and claim queues inside the platform database. |
| `SCALED_EVALS_DATABASE_SCHEMA` | Default `scaled_evals`. Every table lives here. Redundant in a dedicated database, but it keeps the vendored SQL safe to point at a shared one. |
| `CREDENTIALS_ENCRYPTION_KEY` | Fernet key for BYOK credentials. |
| `SCALED_EVALS_RUN_MIGRATIONS` | Default `true`. Set `false` where an external Job owns schema rollout. |

Settings resolve lazily, so the plugin still loads when these are unset; the failure
surfaces on the first request that needs them rather than making the plugin vanish
from service discovery.

## Database and migrations

**scaled-evals runs on its own Postgres.** It shares the platform's *process* but
not its database: the plugin reads `SCALED_EVALS_DATABASE_URL` and never consults the
platform's `DatabaseConfig` or `DATABASE_*` variables. Point it at an empty Postgres
and it does the rest.

The DSN resolves in this order:

1. `SCALED_EVALS_DATABASE_URL`, when set. Every deployment sets it.
2. A `localhost:5432` development default, matching the standalone repo, so a local
   `docker run postgres:16` is the only setup step.

**Postgres is required.** The claim queues need `FOR UPDATE SKIP LOCKED`, plus JSONB,
advisory locks, and enum types, so the platform's own SQLite default is not a usable
target — which is a second reason not to inherit it. When the database is unreachable
the plugin degrades rather than failing the boot: the platform starts normally, other
services are unaffected, and `/v1/readyz` returns `503 degraded`.

Tables live in a `scaled_evals` schema, reached through a `search_path` option that
`resolved_database_url()` appends to the DSN — the one choke point the API pool, both
workers, and the migration applier share. In a dedicated database this is redundant,
and `public` would work; it is kept because the vendored SQL is unqualified, so the
schema is the whole reason this code is *also* safe against a shared database. Startup
creates the schema and then **verifies** the connection resolves there, since Postgres
silently drops an unknown schema from `search_path` instead of erroring.

The plugin migrates on startup, so the database it points at needs no manual
`psql` step. `db/schema` loads only when the schema is fresh
(sentinel: `evaluations`), then every `db/migrations` file is applied in filename
order. The migration set has no version ledger and each file is written to be
re-appliable, so re-applying all of it on each boot is the upstream contract rather
than a shortcut.

**Vendored-SQL divergence:** migrations `001`, `005`, `008`, and `013` had 25 hardcoded
`public` qualifiers (`table_schema = 'public'`, `schemaname = 'public'`,
`to_regclass('public.x')`). These are now `current_schema()` / unqualified so they work
in any schema. Enum literals such as `visibility = 'public'` were left alone.

Concurrent replicas are serialized with a Postgres advisory lock. Migration failure
is logged and **not** raised: an ephemeral plugin should not take the platform API
down because its own database is unreachable, and `/v1/readyz` already reports
`schema` as a required check.

Same logic runs one-shot for a compose service, k8s Job, or manual rollout:

```bash
uv run scaled-evals-migrate            # same resolution order as the plugin
uv run scaled-evals-migrate --dsn ...  # or an explicit target
```

## Routes

| Path | Notes |
|---|---|
| `GET /apis/scaled-evals/healthz` | Plugin liveness stub — static, does not check Postgres |
| `/apis/scaled-evals/v1/{healthz,readyz,metrics}` | Vendored ops probes; `readyz` checks dependencies |
| `/apis/scaled-evals/v1/*` | scaled-evals `/v1` semantics (tasks, evaluations, …) |

**Not mounted:** Switchyard lease/publish (`/v1/switchyard/*`). Switchyard modules remain in-tree for dispatch import compatibility but are out of Phase 1 product surface.

**Removed:** OAuth client discovery (`/v1/auth/config`), which existed only to
hand the CLI login flow the coordinates of a fixed internal identity provider.

There is no second way to serve these routes. The package used to also ship a
standalone FastAPI app (`scaled-evals-api`) that mounted the Switchyard router and
registered the external auth middleware, so installing the package handed you a
command that bypassed the curation above. That app is gone: this service class is
the only HTTP surface, which makes "not mounted" a property of the code rather
than a convention.

## Who a caller is

The plugin does not authenticate anyone. It used to: the standalone service did
OIDC discovery against a fixed internal issuer, fetched JWKS and validated JWT
signatures, ran an OAuth client-credentials exchange, introspected API keys, and
trusted identity headers from a specific private proxy — roughly 700 lines in
`api/auth.py`, plus a CLI that ran authorization-code + PKCE login and cached the
session in the OS keyring.

All of it is gone. The platform authenticates the request before a plugin route
runs, so a second identity provider inside the plugin would be a competing source
of truth. What survives is the ownership model the repositories actually filter
on — `CurrentPrincipal.owner_id` — and one function that produces it.

Consequences worth knowing before you rely on this:

- **`/v1` is single-tenant.** Every caller resolves to owner `dev`, so all
  callers share one view of tasks, evaluations, and credentials. Bridging
  platform identity means setting `request.state.principal` upstream; no route
  changes.
- **`CONTROL_PLANE_AUTH_ENABLED=true` now fails closed with 401** rather than
  gating on a provider. There is nothing left to consult, and silently falling
  back to the shared owner would hand one caller another caller's data.
- **The CLI takes a token, it does not obtain one.** `--token` /
  `SCALED_EVALS_TOKEN` is the only credential source; `scaled-evals auth
  login|status|logout` are gone and `auth whoami` is now top-level
  `scaled-evals whoami`.

## Verify locally (end to end)

**1. Plugin loads.** The `nemo.services` loader swallows import errors, so a broken
plugin disappears with one log line instead of failing loudly — check discovery
explicitly rather than assuming.

```bash
uv run python -c "
from nmp.platform_runner.registry import get_available_services, get_service_groups
print('discovered:', 'scaled-evals' in get_available_services())
print('in groups:', [g for g, v in get_service_groups().items() if 'scaled-evals' in v])
"
uv run pytest plugins/_temporary-scaled-evals/tests/ -q
```

Expect `discovered: True`, `in groups: ['api', 'all']`, passing tests. To include the
real-Postgres migration check, point the suite at a throwaway server — it creates and
drops its own scratch database per run:

```bash
SCALED_EVALS_TEST_DATABASE_URL=postgresql://scaled_evals:scaled_evals@127.0.0.1:5434/scaled_evals \
  uv run pytest plugins/_temporary-scaled-evals/tests/ -q
```

**2. Postgres.** scaled-evals' own, so an empty server is all it needs.

```bash
docker run -d --name scaled-evals-pg \
  -e POSTGRES_USER=scaled_evals -e POSTGRES_PASSWORD=scaled_evals -e POSTGRES_DB=scaled_evals \
  -p 5434:5432 postgres:16
```

**3. Run the platform.** The platform keeps its own default store (SQLite locally);
only scaled-evals is pointed at Postgres. Generating the key via command substitution
keeps it out of shell history.

```bash
export SCALED_EVALS_DATABASE_URL="postgresql://scaled_evals:scaled_evals@127.0.0.1:5434/scaled_evals"
export CREDENTIALS_ENCRYPTION_KEY="$(uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"

uv run nemo services run --services scaled-evals --port 8080
```

Banner should read `Services (1): scaled-evals`. If the port is held by a previous run,
`nemo services stop` first. Startup logs the migration result — `8 schema files` on a
fresh schema, `0 schema files` on every boot after that:

```text
scaled-evals: database ready in schema 'scaled_evals' (8 schema files, 41 migrations)
```

Confirm the tables landed, and that nothing leaked into `public`:

```bash
docker exec scaled-evals-pg psql -U scaled_evals -d scaled_evals -tAc \
  "select table_schema, count(*) from information_schema.tables \
   where table_schema in ('public','scaled_evals') group by 1 order by 1;"
# scaled_evals|19
```

**4. Fire the API.**

```bash
B=http://127.0.0.1:8080/apis/scaled-evals
curl -s $B/healthz
curl -s $B/v1/readyz
curl -s $B/v1/tasks
curl -s -X POST $B/v1/tasks -H 'content-type: application/json' \
  -d '{"name":"smoke-task","description":"phase1 plugin smoke"}'
```

`readyz` returns 503 `degraded` with `postgres: ok` and `schema: ok`. The failing
`object_store`, `buildkit`, `registry`, and `build_worker` checks are expected until
T1.3/T1.5 stand those up; the control plane itself is healthy. `POST /v1/tasks` returns
201 with a presigned upload URL, which needs an object store before the upload
completes.

**5. Teardown.** `nemo services run` spawns a child uvicorn that outlives its parent, so
kill the listener rather than the wrapper.

```bash
lsof -ti tcp:8080 | xargs kill
docker rm -f scaled-evals-pg
```

## Workers (separate processes)

```bash
scaled-evals-build-worker
scaled-evals-dispatch-worker
```

Workers read the same `SCALED_EVALS_DATABASE_URL` and S3 env as the plugin.

## Licensing

Every `.py`, `.sql`, `.sh`, `.yaml`, `.yml`, and `.toml` file carries the
two-line SPDX header the rest of the platform uses. `tests/test_spdx_headers.py`
enforces it over `git ls-files`, and also asserts a shebang still owns line 1 —
inserting a header above `#!` silently stops the kernel honouring it, and nothing
else in the suite would notice.

## Out of this plugin

- Upstream-only evaluation apps and corpora
- Hosted image-admission canary (stubbed no-op)
- Hosted auth sidecars (`auth-router` / `preview-router`)
- Platform image-builder / registry / sandbox plugins (Phase 2)
- nemo-evaluator API fold (Phase 3)
