# Studio plugins — extension hooks

Platform extension system for **slots**, **plugin routes**, and **view overrides**.

**Full developer guide:** [`../docs/plugins.md`](../docs/plugins.md) — how to run plugins, register
manifests, author extensions, and troubleshoot (for humans and agents).

## Quick links

| Topic | Location |
| --- | --- |
| Example plugins (this PR) | `web/packages/studio-plugins-example/` |
| Merge entry | `index.ts` |
| Types & slot ids | `types.ts` |
| Local-only overrides | `manifest.local.ts.example`, `local/README.md` |
| Backend query plugins | `services/intake/.../query_plugins/custom/README.md` |

Enable with `VITE_FF_EXPERIMENT_PLUGINS=true` in `env/.env.dev.local`.
