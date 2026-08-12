// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { usePlugins } from '@studio/plugins/PluginContext';
import { usePluginTraceViews } from '@studio/plugins/PluginTraceViewContext';
import { PluginTraceViewActivity, PluginTraceViewRenderer } from '@studio/plugins/PluginTraceViews';
import type { LoadedPlugin, PluginHost, PluginTraceViewProps } from '@studio/plugins/types';
import { usePluginHost } from '@studio/plugins/usePluginHost';
import { render, renderHook, screen } from '@testing-library/react';

vi.mock('@studio/plugins/PluginContext', () => ({ usePlugins: vi.fn() }));
vi.mock('@studio/plugins/usePluginHost', () => ({ usePluginHost: vi.fn() }));

const HOST = {
  workspaceId: 'default',
  auth: { accessToken: 'token', getAccessToken: () => 'token' },
  sdk: { platform: {} },
  navigation: { navigate: vi.fn(), back: vi.fn() },
  notifications: { notify: vi.fn() },
  telemetry: { info: vi.fn(), warn: vi.fn(), error: vi.fn(), event: vi.fn() },
  breadcrumbs: { set: vi.fn() },
} as unknown as PluginHost;

const Root = () => null;
const navItems = () => [];

const TraceView = ({ host, trace }: PluginTraceViewProps) => (
  <div>
    view:{host.workspaceId}:{trace.sessionId}:{trace.id}
  </div>
);

const TraceActivity = ({ trace }: PluginTraceViewProps) => <div>activity:{trace.id}</div>;

const plugin: LoadedPlugin = {
  name: 'zoomer',
  Root,
  navItems,
  traceViews: [
    {
      id: 'semantic-map',
      label: 'Zoomer',
      View: TraceView,
      Activity: TraceActivity,
    },
  ],
};

beforeEach(() => {
  vi.mocked(usePlugins).mockReturnValue([plugin]);
  vi.mocked(usePluginHost).mockReturnValue(HOST);
});

describe('plugin trace views', () => {
  it('resolves plugin-scoped modes from loaded bundle exports', () => {
    const { result } = renderHook(usePluginTraceViews);

    expect(result.current).toHaveLength(1);
    expect(result.current[0]).toMatchObject({
      pluginName: 'zoomer',
      id: 'semantic-map',
      label: 'Zoomer',
      mode: 'plugin:zoomer:semantic-map',
    });
  });

  it('renders the selected view and compact activity with the shared host', () => {
    const { result } = renderHook(usePluginTraceViews);
    const view = result.current[0];
    const trace = { id: 'trace-1', sessionId: 'session-1' };

    render(
      <>
        <PluginTraceViewRenderer view={view} trace={trace} />
        <PluginTraceViewActivity view={view} trace={trace} />
      </>
    );

    expect(screen.getByText('view:default:session-1:trace-1')).toBeInTheDocument();
    expect(screen.getByText('activity:trace-1')).toBeInTheDocument();
    expect(usePluginHost).toHaveBeenCalledWith('zoomer');
  });
});
