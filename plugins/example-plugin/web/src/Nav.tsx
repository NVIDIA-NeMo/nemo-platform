import type { PluginNavGroup } from './types';

/**
 * Returns the nav groups for this plugin.
 *
 * Each item's `href` is an absolute path that Studio's side nav renders as a
 * link.  Sub-pages are just deeper paths within the plugin's route subtree
 * (`/workspaces/:id/plugin/example/*`).
 */
export const navItems = (workspaceId: string): PluginNavGroup[] => [
  {
    group: 'Example Plugin',
    items: [
      {
        id: 'example-overview',
        iconName: 'flask-conical',
        label: 'Overview',
        href: `/workspaces/${workspaceId}/plugin/example/overview`,
      },
      {
        id: 'example-auth',
        iconName: 'key-round',
        label: 'Auth',
        href: `/workspaces/${workspaceId}/plugin/example/auth`,
      },
      {
        id: 'example-workspace',
        iconName: 'building-2',
        label: 'Workspace',
        href: `/workspaces/${workspaceId}/plugin/example/workspace`,
      },
    ],
  },
];
