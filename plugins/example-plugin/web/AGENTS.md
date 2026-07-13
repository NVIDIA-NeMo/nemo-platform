# Studio plugin web UI — agent instructions

This is the web UI for a NeMo Studio plugin. Studio loads the built bundle at
runtime and renders it **inside its own React tree**. This dir is also the
canonical template other plugins copy — keep it exemplary.

Runtime contract: `../../../web/packages/studio/src/plugins/types.ts`.

## Mental model

- **One root, not two.** Export a `Root` **component**; Studio renders `<Root/>`
  under its own Router / QueryClient / KaizenThemeProvider. Never call
  `createRoot`, never create a `BrowserRouter`.
- **Share the singletons that carry context** — React, react-dom, react-router,
  and `@nvidia/foundations-react-core` resolve via Studio's import map. This dir
  **externalizes** them so the plugin uses Studio's one instance (shared router +
  theme). Everything else bundles privately.

## Rules — DO / DON'T

| Concern | DO | DON'T |
| --- | --- | --- |
| Entry | `export { Root }` (component) + `export { navItems }` from `src/index.ts` | export `mount()` or call `createRoot` |
| Routing | Studio's shared router — `Routes`/`Route`/`NavLink`/`Navigate`/`Outlet`/`useNavigate`, paths relative to the plugin mount | `BrowserRouter`, `history.pushState` patching, hardcoded `basename` |
| Components | KUI from `@nvidia/foundations-react-core` — `Text`, `Stack`, `Flex`, `Button` | hand-rolled styled `<div>`s or native `<button>` |
| Styling | Studio's theme-aware tokens: `bg-surface-base/raised/sunken/hover`, `text-subtle/muted/primary`, `border-subtle` | hardcoded Tailwind palette (`bg-gray-100`, `text-blue-700`) — not compiled for the plugin, not theme-aware |
| Auth | `host.auth.getAccessToken()` **per request** → `Authorization: Bearer …` | `react-oidc-context` / `useAuth` (refresh token must not cross the boundary) |
| Deps | externalize the shared set in `vite.config.ts`; bundle the rest | bundle react / react-dom / react-router / foundations |

Studio injects everything a plugin needs through a **single `host` prop**
(`host.workspaceId`, `host.auth`, `host.sdk`, `host.navigation`,
`host.notifications`, `host.telemetry`) — grouped so new capabilities extend the
handle without changing `Root`'s signature. Destructure what you use. All are
backed by Studio's own singletons: `notifications` fires into Studio's shared
toaster, `telemetry` logs to Studio's OTEL pipeline (auto-scoped to the plugin),
`navigation` drives Studio's shared router.

`@tanstack/react-query` **is** shared — call `useQuery`/`useMutation` and it reads
Studio's `QueryClientProvider` (one cache across Studio and every plugin). Put the
`host.auth.getAccessToken()` Bearer token in your `queryFn`.

Studio's **SDK** arrives on `host.sdk`, not via an import. `host.sdk.platform` is
the platform service's generated hooks; call them at the top level like any hook
(e.g. `host.sdk.platform.useEntitiesListWorkspaces({ page: 1, page_size: 100 })`,
see `src/Root.tsx`). They run on Studio's one configured axios instance (base URL +
OIDC interceptor) and the shared QueryClient — a plugin never bundles or
configures the SDK itself. This works because React is a shared singleton, so a
hook from Studio's module graph dispatches into the plugin's tree. `@nemo/sdk` is
a private, unpublished package, so it is **not** a dependency here: `src/types.ts`
declares a minimal structural `PluginSdk` covering only the hooks this example
calls. A real plugin either mirrors the calls it needs the same way or, if it can
resolve the SDK's types, types `host.sdk` as Studio does.

## Contract

```ts
// PluginRootProps (from Studio's types.ts)
{
  host: {
    workspaceId: string;
    auth: { accessToken: string; getAccessToken: () => string };
    sdk: { platform: /* @nemo/sdk platform hooks */ };
    navigation: { navigate: (to: string) => void; back: () => void };
    notifications: { notify: (message: string, type?: 'success'|'error'|'info'|'warning') => void };
    telemetry: { info; warn; error: (m, cause?) => void; event: (name, attrs?) => void };
  };
}
```

`src/index.ts` must export `Root` (a `ComponentType<PluginRootProps>`) and
`navItems(workspaceId) => PluginNavGroup[]`. See `src/Root.tsx` and `src/Nav.tsx`.

## Externals

The `external` list in `vite.config.ts` **must match** Studio's `VENDOR_EXTERNALS`
in `../../../web/packages/studio/vite.config.ts`. If Studio adds a shared
singleton, add it here too or the plugin bundles its own copy and loses the
shared instance/theme. The SDK is **not** in this list — it comes in on the `sdk`
prop (see above), so there is nothing to externalize for it.

## Build & verify

```bash
npm install          # first time — pulls @nvidia/foundations-react-core etc.
npm run build        # emits ../src/<pkg>/web/dist/index.js (shipped in the wheel)

# shared deps must stay external (bare specifiers, not bundled):
grep -oE 'from *"[^"]*"' ../src/<pkg>/web/dist/index.js | sort -u
```

The bundle is registered via the plugin's `nemo.studio` entry point
(`studio.py` → `StudioSpec`), served at `/plugin-ui/<name>/index.js`, and the
UI route is gated behind the `pluginsEnabled` flag (on by default).

## Gotchas

- **Token classes must be ones Studio already compiles.** Studio's Tailwind only
  scans `web/packages/**`, not this dir. Stick to the semantic tokens Studio uses
  (grep `web/packages/studio/src` for `bg-surface`, `text-subtle`) and KUI
  components (self-styled). Arbitrary utility classes won't have CSS.
- **Never expose refresh tokens.** Only `accessToken` / `getAccessToken` cross the
  boundary — never reach for Studio's OIDC context.
- **New shared singletons** with internal dynamic imports need `codeSplitting:
  false` in Studio's vendor build; here you only add the name to `external`.
