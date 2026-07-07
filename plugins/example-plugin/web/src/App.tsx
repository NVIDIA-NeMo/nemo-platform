import React from 'react';
import { BrowserRouter, Routes, Route, NavLink, Navigate, Outlet } from 'react-router-dom';

interface AppProps {
  workspaceId: string;
  accessToken: string;
  basename: string;
}

/**
 * Example plugin app.
 *
 * This component is mounted by `mount()` into a container div owned by Studio's
 * PluginRenderer. Since it is rendered via `createRoot` in an isolated React tree,
 * it cannot access Studio's router context — hence the explicit `<BrowserRouter>`
 * here. The plugin owns its own routing within the `/plugin/example/*` subtree.
 *
 * Navigation between plugin pages:
 * - The Studio side nav uses the `href` values from `navItems()` as plain anchor
 *   links, so clicking a side nav item causes a full URL change that React Router
 *   picks up inside this BrowserRouter.
 * - Links *within* plugin pages use React Router's `<NavLink>` / `<Link>` for
 *   client-side navigation without a full page reload.
 *
 * The `accessToken` prop is available for authenticated API calls, e.g.:
 *   fetch('/apis/my-resource', { headers: { Authorization: `Bearer ${accessToken}` } })
 */
export function App({ workspaceId, accessToken, basename }: AppProps) {
  const base = `/workspaces/${workspaceId}/plugin/example`;

  return (
    <BrowserRouter basename={basename}>
      <Routes>
        <Route path={`${base}/*`} element={<Layout base={base} />}>
          <Route index element={<Navigate to="overview" replace />} />
          <Route path="overview" element={<OverviewPage />} />
          <Route path="auth" element={<AuthPage accessToken={accessToken} />} />
          <Route path="workspace" element={<WorkspacePage workspaceId={workspaceId} accessToken={accessToken} />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

/** Shared shell with an in-plugin tab bar demonstrating client-side navigation. */
function Layout({ base }: { base: string }) {
  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `px-3 py-1 rounded text-sm font-medium ${isActive ? 'bg-blue-100 text-blue-700' : 'text-gray-600 hover:text-gray-900'}`;

  return (
    <div className="flex flex-col h-full p-4 gap-4">
      {/*
       * In-plugin tab bar — uses <NavLink> for client-side navigation within
       * the plugin's BrowserRouter. This is independent of Studio's router.
       */}
      <nav className="flex gap-2 border-b pb-2">
        <NavLink to="overview" className={linkClass}>Overview</NavLink>
        <NavLink to="auth" className={linkClass}>Auth</NavLink>
        <NavLink to="workspace" className={linkClass}>Workspace</NavLink>
      </nav>
      <div className="flex-1">
        <Outlet />
      </div>
    </div>
  );
}

function OverviewPage() {
  return (
    <div className="space-y-2">
      <h1 className="text-lg font-semibold">Example Plugin</h1>
      <p className="text-sm text-gray-500">
        This is an example Studio plugin. Use the tabs above or the Studio side
        nav to explore what information is available to a plugin at runtime.
      </p>
    </div>
  );
}

function AuthPage({ accessToken }: { accessToken: string }) {
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
    <div className="space-y-3">
      <h1 className="text-lg font-semibold">Auth</h1>
      <p className="text-sm text-gray-500">
        Studio passes an OIDC access token to every plugin via{' '}
        <code>mount(container, {'{ auth: { accessToken } }'})</code>. Use it as a
        Bearer token when calling platform APIs.
      </p>

      <div className="space-y-1">
        <h2 className="text-sm font-medium text-gray-700">Example API call</h2>
        <pre className="text-xs bg-gray-100 rounded p-3 overflow-x-auto">{`fetch('/apis/v1/workspaces', {
  headers: { Authorization: \`Bearer \${accessToken}\` },
})`}</pre>
      </div>

      <div className="space-y-1">
        <h2 className="text-sm font-medium text-gray-700">Token claims (decoded, not verified)</h2>
        {claims ? (
          <pre className="text-xs bg-gray-100 rounded p-3 overflow-x-auto">
            {JSON.stringify(claims, null, 2)}
          </pre>
        ) : (
          <p className="text-xs text-gray-400">
            {accessToken ? 'Could not decode token.' : 'No token provided.'}
          </p>
        )}
      </div>
    </div>
  );
}

function WorkspacePage({ workspaceId, accessToken }: { workspaceId: string; accessToken: string }) {
  return (
    <div className="space-y-3">
      <h1 className="text-lg font-semibold">Workspace</h1>
      <p className="text-sm text-gray-500">
        Studio passes the current workspace ID to every plugin via{' '}
        <code>mount(container, {'{ workspaceId }'})</code>.
      </p>

      <div className="space-y-1">
        <h2 className="text-sm font-medium text-gray-700">Current workspace</h2>
        <pre className="text-xs bg-gray-100 rounded p-3">{workspaceId}</pre>
      </div>

      <div className="space-y-1">
        <h2 className="text-sm font-medium text-gray-700">Example API call scoped to this workspace</h2>
        <pre className="text-xs bg-gray-100 rounded p-3 overflow-x-auto">{`fetch(\`/apis/v1/workspaces/\${workspaceId}/models\`, {
  headers: { Authorization: \`Bearer \${accessToken}\` },
})`}</pre>
      </div>
    </div>
  );
}

function NotFound() {
  return <p className="text-sm text-gray-500">Page not found.</p>;
}
