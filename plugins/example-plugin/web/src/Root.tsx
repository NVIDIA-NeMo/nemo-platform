// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Flex, Stack, Text } from '@nvidia/foundations-react-core';
import { Routes, Route, NavLink, Navigate, Outlet } from 'react-router-dom';
import type { PluginRootProps, PluginSdk } from './types';

/**
 * Example plugin root.
 *
 * Studio renders this component inside its own React tree (under Studio's
 * Router, QueryClient, and KaizenThemeProvider), so the plugin shares those
 * contexts. It uses Studio's router directly (no `BrowserRouter`) and Studio's
 * design system — KUI components from `@nvidia/foundations-react-core` plus
 * Studio's semantic token classes (`bg-surface-*`, `text-subtle`, ...) — which
 * are theme-aware, so the plugin follows Studio's light/dark theme for free.
 * Both react-router and foundations are shared singletons via Studio's import
 * map; the plugin bundles neither.
 *
 * Studio injects the `host` prop — `host.workspaceId`, `host.auth`, and
 * `host.sdk` (typed hooks on Studio's authenticated axios + shared QueryClient;
 * call them directly, see `OverviewPage`).
 *
 * Call `host.auth.getAccessToken()` per request (not once at render) so calls keep
 * working after OIDC silent renew rotates the token, e.g.:
 *   fetch('/apis/my-resource', { headers: { Authorization: `Bearer ${getAccessToken()}` } })
 */
export function Root({ host }: PluginRootProps) {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="overview" replace />} />
        <Route path="overview" element={<OverviewPage sdk={host.sdk} />} />
        <Route path="auth" element={<AuthPage getAccessToken={host.auth.getAccessToken} />} />
        <Route path="workspace" element={<WorkspacePage workspaceId={host.workspaceId} />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}

/** Shared shell with an in-plugin tab bar demonstrating client-side navigation. */
function Layout() {
  // Active/inactive styling uses Studio's semantic tokens so it tracks the theme.
  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `px-3 py-1 rounded text-sm font-medium transition-colors ${
      isActive ? 'text-primary bg-surface-hover' : 'text-subtle hover:text-primary'
    }`;

  return (
    <Stack gap="4" className="h-full p-4">
      {/* In-plugin tab bar — uses Studio's shared react-router <NavLink>. */}
      <Flex gap="2" className="border-b border-subtle pb-2">
        <NavLink to="overview" className={linkClass}>Overview</NavLink>
        <NavLink to="auth" className={linkClass}>Auth</NavLink>
        <NavLink to="workspace" className={linkClass}>Workspace</NavLink>
      </Flex>
      <div className="flex-1">
        <Outlet />
      </div>
    </Stack>
  );
}

/** Code sample block styled with Studio's surface tokens (theme-aware). */
function CodeBlock({ children }: { children: string }) {
  return (
    <pre className="bg-surface-sunken text-subtle rounded p-3 text-xs overflow-x-auto font-mono">
      {children}
    </pre>
  );
}

function OverviewPage({ sdk }: { sdk: PluginSdk }) {
  // Studio's typed hook — runs on Studio's authenticated axios + shared cache.
  const { data, isPending, isError } = sdk.platform.useEntitiesListWorkspaces(
    { page: 1, page_size: 100 },
    { query: { staleTime: 5_000 } }
  );
  const workspaces = data?.data ?? [];

  return (
    <Stack gap="2">
      <Text kind="label/bold/lg">Example Plugin</Text>
      <Text kind="body/regular/sm" color="secondary">
        This is an example Studio plugin. Use the tabs above or the Studio side
        nav to explore what information is available to a plugin at runtime.
      </Text>

      <Stack gap="1">
        <Text kind="label/bold/sm">Shared SDK</Text>
        <Text kind="body/regular/xs" color="secondary">
          Listed via Studio&apos;s sdk.platform.useEntitiesListWorkspaces() — the
          platform&apos;s typed hook, running on Studio&apos;s authenticated axios
          and shared QueryClient rather than a plugin copy.
        </Text>
        {isPending ? (
          <Text kind="body/regular/xs" color="secondary">Loading…</Text>
        ) : isError ? (
          <Text kind="body/regular/xs" color="danger">Request failed.</Text>
        ) : (
          <Text kind="body/regular/sm">
            {workspaces.length} workspaces: {workspaces.map((w) => w.name).join(', ')}
          </Text>
        )}
      </Stack>
    </Stack>
  );
}

function AuthPage({ getAccessToken }: { getAccessToken: () => string }) {
  const accessToken = getAccessToken();
  // Parse the JWT payload (without verification — for display only).
  let claims: Record<string, unknown> | null = null;
  try {
    const payload = accessToken.split('.')[1];
    if (payload) {
      claims = JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/'))) as Record<string, unknown>;
    }
  } catch {
    // malformed token — show raw
  }

  return (
    <Stack gap="3">
      <Text kind="label/bold/md">Auth</Text>
      <Text kind="body/regular/sm" color="secondary">
        Studio passes an OIDC access token to every plugin via the plugin&apos;s
        auth prop. Call getAccessToken() per request — it returns the current
        token after silent renewal — and use it as a Bearer token.
      </Text>

      <Stack gap="1">
        <Text kind="label/bold/sm">Example API call</Text>
        <CodeBlock>{`fetch('/apis/v1/workspaces', {
  headers: { Authorization: \`Bearer \${getAccessToken()}\` },
})`}</CodeBlock>
      </Stack>

      <Stack gap="1">
        <Text kind="label/bold/sm">Token claims (decoded, not verified)</Text>
        {claims ? (
          <CodeBlock>{JSON.stringify(claims, null, 2)}</CodeBlock>
        ) : (
          <Text kind="body/regular/xs" color="secondary">
            {accessToken ? 'Could not decode token.' : 'No token provided.'}
          </Text>
        )}
      </Stack>
    </Stack>
  );
}

function WorkspacePage({ workspaceId }: { workspaceId: string }) {
  return (
    <Stack gap="3">
      <Text kind="label/bold/md">Workspace</Text>
      <Text kind="body/regular/sm" color="secondary">
        Studio passes the current workspace ID to every plugin via the plugin&apos;s
        workspaceId prop.
      </Text>

      <Stack gap="1">
        <Text kind="label/bold/sm">Current workspace</Text>
        <CodeBlock>{workspaceId}</CodeBlock>
      </Stack>

      <Stack gap="1">
        <Text kind="label/bold/sm">Example API call scoped to this workspace</Text>
        <CodeBlock>{`fetch(\`/apis/v1/workspaces/\${workspaceId}/models\`, {
  headers: { Authorization: \`Bearer \${getAccessToken()}\` },
})`}</CodeBlock>
      </Stack>
    </Stack>
  );
}

function NotFound() {
  return (
    <Text kind="body/regular/sm" color="secondary">
      Page not found.
    </Text>
  );
}
