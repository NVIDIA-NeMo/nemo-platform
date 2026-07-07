import React from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import type { PluginMountProps } from './types';

/**
 * Mount the example plugin into `container`.
 *
 * The plugin creates its own React root (intentional isolation — each plugin
 * manages its own React instance so it cannot conflict with Studio's version
 * or with other plugins).
 *
 * Returns the cleanup function that unmounts the plugin and releases all resources.
 *
 * ## Navigation sync
 *
 * React Router's BrowserRouter detects URL changes via `popstate` events, but
 * programmatic navigation (Studio's NavLink clicks) calls `history.pushState()`
 * directly without firing `popstate`. The plugin patches both `pushState` and
 * `replaceState` to dispatch a synthetic `popstate` so this plugin's
 * BrowserRouter reacts to Studio-driven navigation. The originals are restored
 * on unmount.
 */
export function mount(container: HTMLElement, props: PluginMountProps): () => void {
  const origPushState = window.history.pushState.bind(window.history);
  const origReplaceState = window.history.replaceState.bind(window.history);

  function firePopState(state: unknown) {
    window.dispatchEvent(new PopStateEvent('popstate', { state }));
  }

  window.history.pushState = (state, ...rest: [string, (string | URL)?]) => {
    origPushState(state, ...rest);
    firePopState(state);
  };

  window.history.replaceState = (state, ...rest: [string, (string | URL)?]) => {
    origReplaceState(state, ...rest);
    firePopState(state);
  };

  const root = createRoot(container);
  root.render(
    React.createElement(App, {
      workspaceId: props.workspaceId,
      accessToken: props.auth.accessToken,
      basename: props.basename,
    }),
  );

  return () => {
    window.history.pushState = origPushState;
    window.history.replaceState = origReplaceState;
    root.unmount();
  };
}
