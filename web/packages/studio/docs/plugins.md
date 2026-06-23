# NeMo Studio plugins — developer guide

How to **run**, **register**, and **extend** NeMo Studio with UI plugins and backend query plugins.
For agents: read this file before changing anything under `web/packages/studio/src/plugins/`,
`web/packages/studio-plugins-example/`, or `services/intake/src/nmp/intake/query_plugins/`.

---

## What you get

| Layer | What it does | Status |
| --- | --- | --- |
| **UI plugin** | Slots, routes, view overrides in Studio | Prototype (`VITE_FF_EXPERIMENT_PLUGINS`) |
| **Query plugin** | Typed ClickHouse fetches via intake API | Prototype (additive to rollups) |

Cross-tier features (e.g. experiment error report) pair a UI plugin with one or more query plugins
over HTTP — shared ids, no cross-import between Python and TypeScript.

---

## How registration works

Plugins are **not** hardcoded in platform hosts. Two peer manifests merge at startup/build time.

```
┌─────────────────────────────────────────────────────────────────┐
│  Studio (frontend)                                              │
│  STUDIO_PLUGINS = core + manifest.local + external              │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP (query plugins only)
┌────────────────────────────▼────────────────────────────────────┐
│  Intake (backend)                                               │
│  QUERY_PLUGINS = registry_local + NEMO_QUERY_PLUGINS_MODULES    │
└─────────────────────────────────────────────────────────────────┘
```

### UI plugins — three sources (merged in order)

Defined in `web/packages/studio/src/plugins/index.ts`:

| Source | File / env | Tracked in git? | Default |
| --- | --- | --- | --- |
| Core | `manifest.core.ts` | Yes | `[]` |
| Local-only | `manifest.local.ts` | No (gitignored) | `[]` if missing |
| External | `@nemo/studio-plugins-external` | Depends | Example package (see below) |

**First registration wins** when two entries share the same plugin `id`.

#### 1. Example package (default for this PR)

Committed at `web/packages/studio-plugins-example/`. Vite resolves
`@nemo/studio-plugins-external` → `studio-plugins-example/src/manifest.ts` automatically in dev
and production builds (see `web/packages/studio/vite.config.ts`).

No env var required for local dev.

#### 2. Local-only UI plugins (optional, gitignored)

For private add-ons on top of the example package:

1. Add code under `web/packages/studio/src/plugins/local/` (gitignored).
2. Copy `manifest.local.ts.example` → `manifest.local.ts` (gitignored).
3. Register plugins in `LOCAL_STUDIO_PLUGINS`.
4. Restart the dev server.

#### 3. Org package at build time

```bash
export NEMO_STUDIO_PLUGINS_ENTRY=/path/to/my-org-plugins/src/manifest.ts
pnpm --filter nemo-studio-ui build --mode fastapi
```

Org manifest must export:

```typescript
export const studioPlugins: StudioPlugin[] = [/* ... */];
```

### Backend query plugins — two sources

Defined in `services/intake/src/nmp/intake/query_plugins/registry.py`:

| Source | File / env | Tracked in git? |
| --- | --- | --- |
| Local dev | `custom/registry_local.py` | No (gitignored) |
| Deploy | `NEMO_QUERY_PLUGINS_MODULES=org.package.registry` | Org package |

Plugin modules live in gitignored `custom/*.py` locally (see `custom/README.md`).

**Restart intake** after changing registration. Verify:

```bash
curl -s "http://127.0.0.1:8080/apis/intake/v2/workspaces/default/query-plugins" | jq .
```

Registered ids appear in `query_plugins[].id`. Dynamic routes are created per id:
`GET …/query-plugins/{query_plugin_id}?experiment_id=…`.

---

## Extension types (UI)

| Type | API | Host |
| --- | --- | --- |
| **Slot** | `contribute({ slot, id, render })` | `<PluginSlot slot="…" context={…} />` |
| **Route** | `routes: [{ id, path, render }]` | Merged in `routes/index.tsx` |
| **View override** | `overrideView({ viewId, render })` | `<PluginViewHost viewId="…" fallback={…} />` |

Slot and view ids are typed in `web/packages/studio/src/plugins/types.ts` (`SlotContextMap`,
`ViewContextMap`). Add a slot there before mounting a new `<PluginSlot />`.

All UI extensions are gated by `VITE_FF_EXPERIMENT_PLUGINS`. When the flag is off, hosts render
exactly as before.

### Workspace scoping

Each `StudioPlugin` may set `workspaces`:

| Value | Effect |
| --- | --- |
| *(omitted)* | `['default']` only |
| `'all'` | Every workspace |
| `['default', 'agent00']` | Listed workspaces only |

Filtering uses the workspace segment from the route (`useWorkspaceFromPath`).

---

## Author a new UI plugin

1. Create a folder under `web/packages/studio-plugins-example/src/` (or your org package).
2. Export a `StudioPlugin` using `contribute()` / `overrideView()` from `@studio/plugins/types`.
3. Import shared Studio utilities via `@studio/…` paths (components, hooks, routes) — the example
   package is bundled as part of the Studio Vite graph.
4. Register the instance in `studio-plugins-example/src/manifest.ts` (or org manifest).
5. Set `workspaces` appropriately.
6. Restart the dev server.

For a **cross-tier** feature, also add a query plugin (below) and call it from the UI via the
generated SDK hooks after OpenAPI refresh.

---

## Author a new query plugin

1. Add `services/intake/src/nmp/intake/query_plugins/custom/my_plugin.py` implementing `QueryPlugin`.
2. Register in `custom/registry_local.py`:
   ```python
   QUERY_PLUGINS = [MyQueryPlugin(), ...]
   ```
3. Restart intake.
4. Define response TypeScript types in your Studio plugin package and call the generic endpoint
   via `useQueryPlugin` (see `studio-plugins-example/src/queryPlugin/useQueryPlugin.ts`). Platform
   OpenAPI exposes only the manifest + generic `{query_plugin_id}` route — not per-plugin schemas.
5. Regenerate SDK when the generic contract changes (not for each new plugin):
   ```bash
   make refresh-openapi
   cd web && pnpm --filter @nemo/sdk gen:platform && pnpm --filter @nemo/sdk gen:platform-zod
   ```

Run tests:

```bash
uv run pytest services/intake/tests/test_query_plugins.py -v
```

Framework tests always run; plugin-specific tests skip when `registry_local.py` is absent.

---

---

## Key paths (agents)

| Artifact | Path |
| --- | --- |
| UI types & registry | `web/packages/studio/src/plugins/` |
| Example UI plugins (PR) | `web/packages/studio-plugins-example/src/` |
| UI merge entry | `web/packages/studio/src/plugins/index.ts` |
| Vite manifest resolution | `web/packages/studio/vite.config.ts` (`studioPluginManifestAlias`) |
| Feature flag | `web/packages/studio/src/constants/featureFlags/featureFlags.ts` |
| Query plugin framework | `services/intake/src/nmp/intake/query_plugins/` |
| Query plugin API | `services/intake/src/nmp/intake/api/v2/query_plugins/endpoints.py` |
| Local query manifest template | `services/intake/.../custom/registry_local.py.example` |
| OpenAPI (after API changes) | `openapi/openapi.yaml` |

### Do not commit (local/org-owned)

- `web/packages/studio/src/plugins/manifest.local.ts`
- `web/packages/studio/src/plugins/local/**` (except README)
- `services/intake/.../query_plugins/custom/*.py` (except `*.example.py`, README)

Platform PRs ship **hooks + example package**; org plugins move to a sibling repo before upstream
merge.

---

## FastAPI / production-shaped builds

To serve Studio from the platform gateway with plugins baked in:

```bash
export NEMO_STUDIO_PLUGINS_ENTRY=/path/to/manifest.ts   # optional; defaults to example package
cd web && pnpm --filter nemo-studio-ui build --mode fastapi
```

Plugin code is static after build. Changing manifests requires a rebuild.


## Run example plugins locally

### Prerequisites

1. **ClickHouse** — required for intake telemetry and query plugins:
   ```bash
   services/intake/scripts/spans/run_clickhouse.sh
   ```
2. **Backend** — intake must be in the service set:
   ```bash
   export NMP_BASE_URL=http://localhost:8080
   uv run nemo services run \
     --services entities,secrets,models,inference-gateway,intake \
     --controllers models
   ```
   Wait for `curl -sf http://127.0.0.1:8080/health/ready`.
3. **Studio feature flag** — in `web/packages/studio/env/.env.dev.local`:
   ```bash
   VITE_FF_EXPERIMENT_PLUGINS=true
   VITE_PLATFORM_BASE_URL=http://127.0.0.1:8080
   ```

### Start Studio (Vite dev — recommended for plugin work)

From repo root:

```bash
cd web
pnpm install
VITE_PLATFORM_BASE_URL=http://127.0.0.1:8080 pnpm --filter nemo-studio-ui start:dev -- --force
```

### Seed demo data (optional)

```bash
# Error-span demo (experiment-errors plugin)
uv run python services/intake/scripts/spans/seed_error_traces.py --base-url http://127.0.0.1:8080

# agent00 workspace traces (intake-trace-detail-agent00 plugin)
uv run python services/intake/scripts/spans/seed_agent00_traces.py --base-url http://127.0.0.1:8080
```

### Golden demo paths

| Workspace | Where to go | Plugin |
| --- | --- | --- |
| `default` | Experiment group page | `experiment-insights` — cost vs latency chart |
| `default` | Experiment detail page | `experiment-errors` — error banner |
| `default` | Error report route (from banner) | `experiment-errors` — two query-plugin tables |
| `default` | Intake trace detail | `intake-trace-detail` — full view override |
| `agent00` | Intake trace detail | `intake-trace-detail-agent00` — simplified override |

Workspace is the name in the URL: `/workspaces/default/...` vs `/workspaces/agent00/...`.


---

## Related docs

- `web/packages/studio/src/plugins/README.md` — short index
- `web/packages/studio-plugins-example/README.md` — example plugin list
- `services/intake/src/nmp/intake/query_plugins/custom/README.md` — backend local manifest
