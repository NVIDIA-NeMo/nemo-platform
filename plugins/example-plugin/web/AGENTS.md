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
| Auth | `props.auth.getAccessToken()` **per request** → `Authorization: Bearer …` | `react-oidc-context` / `useAuth` (refresh token must not cross the boundary) |
| Deps | externalize the shared set in `vite.config.ts`; bundle the rest | bundle react / react-dom / react-router / foundations |

`@tanstack/react-query` **is** shared — call `useQuery`/`useMutation` and it reads
Studio's `QueryClientProvider` (one cache across Studio and every plugin). Put the
`auth.getAccessToken()` Bearer token in your `queryFn`.

## Contract

```ts
// PluginRootProps (from Studio's types.ts)
{ workspaceId: string; auth: { accessToken: string; getAccessToken: () => string } }
```

`src/index.ts` must export `Root` (a `ComponentType<PluginRootProps>`) and
`navItems(workspaceId) => PluginNavGroup[]`. See `src/Root.tsx` and `src/Nav.tsx`.

## Externals

The `external` list in `vite.config.ts` **must match** Studio's `VENDOR_EXTERNALS`
in `../../../web/packages/studio/vite.config.ts`. If Studio adds a shared
singleton, add it here too or the plugin bundles its own copy and loses the
shared instance/theme.

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
