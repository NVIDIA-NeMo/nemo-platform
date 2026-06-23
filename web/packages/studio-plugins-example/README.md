# Example Studio plugins (prototype PR)

Reference plugins for the Studio extension system. **Committed temporarily** so this PR can demo
slots, routes, and view overrides end-to-end.

| Plugin | What it does |
| --- | --- |
| `experiment-insights` | Cost vs latency chart on experiment group |
| `experiment-errors` | Error banner + error report route |
| `intake-trace-detail` | Trace detail view override (`default` workspace) |
| `intake-trace-detail-agent00` | Simplified trace detail (`agent00` workspace) |

## Loading

`nemo-studio-ui` resolves `@nemo/studio-plugins-external` to `src/manifest.ts` here by default
(see `packages/studio/vite.config.ts`). Override with:

```bash
export NEMO_STUDIO_PLUGINS_ENTRY=/path/to/org/manifest.ts
```

Matching backend query plugins live under
`services/intake/src/nmp/intake/query_plugins/custom/` (local manifest).

See **`web/packages/studio/docs/plugins.md`** for the full run and registration guide.

## Later

Move this package to an org repo and drop it from the platform tree before upstream merge.
