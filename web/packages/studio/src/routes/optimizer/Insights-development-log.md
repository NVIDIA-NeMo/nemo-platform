# Insights — Development Log

A running log of non-obvious decisions and gotchas for the Optimizer **Insights** UI
(`web/packages/studio/src/routes/optimizer/`). Read this before extending the section.

---

## API types are hand-written, not generated (2026-07-07)

The Optimizer is a backend **plugin** (`nemo-optimizer-plugin`, external repo
`~/Sites/optimizer/NeMo-Optimizer`). Studio consumes its HTTP API at
`/apis/optimizer/v2/workspaces/{workspace}/insights`, but the plugin's OpenAPI is **not**
part of the generated SDK (`@nemo/sdk`). So `api/optimizer.ts` is hand-written: the
`Insight` type and the `useOptimizerListInsights` hook are maintained by hand, calling the
shared authenticated `customFetch` from `@nemo/sdk/generated/fetchers/platform`.

**Consequence:** these types are not checked against the backend schema. If the plugin's
`Insight` entity changes, `api/optimizer.ts` will silently drift until it breaks at runtime.

**Proper long-term fix (enhancement, not a correction):** add the optimizer plugin's OpenAPI
to the SDK generation pipeline so the types/hooks are generated like every other service.
Until then, keep `api/optimizer.ts` in sync with the plugin's `entities.py` / `schema.py`.

---

## Getting the backend plugin loaded (2026-07-07)

The optimizer routes only exist if `nemo-optimizer-plugin` is installed into the platform's
venv. It is **not** in `plugins/` — it's an external repo (`~/Sites/optimizer/NeMo-Optimizer`),
so checking out this Studio branch alone gives you a UI with nothing to call (404s / empty state).

Two snags make a plain install fail:

1. The plugin pins `requires-python >=3.12`, but the local platform venv is **Python 3.11**.
2. Its `OptimizerService` route path imports `pydantic_ai` / `pydantic_ai_harness`, which
   aren't in the platform venv. (It does **not** need the internal `nemo_oo_agents` git dep to
   serve routes — that's only used by `experimentalist/`, i.e. actually running analyze jobs.)

Install sequence that works (from `~/Sites/nemo-platform`):

```bash
uv pip install --python .venv/bin/python \
  "pydantic-ai-slim[anthropic]>=1.0" "pydantic-ai-harness[code-mode]>=0.3.0"
# pip, not uv: uv has no --ignore-requires-python; --no-deps avoids clobbering the
# source-built nemo-platform and skips the internal nemo_oo_agents git dependency.
.venv/bin/pip install --no-deps --ignore-requires-python -e ~/Sites/optimizer/NeMo-Optimizer
# then restart the platform so entry points re-register:
nemo services run --host 127.0.0.1 --port 8080
```

Verify: `curl http://localhost:8080/apis/optimizer/v2/workspaces/default/insights` → `200`.

**Caveat:** running on 3.11 bypasses the plugin's 3.12 pin. It imports fine on the route path
today; the real fix if 3.12-only syntax ever bites is a 3.12 platform venv.
