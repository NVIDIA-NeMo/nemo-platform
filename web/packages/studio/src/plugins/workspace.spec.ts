// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { buildSlotIndex, buildViewIndex } from '@studio/plugins/registry';
import { contribute, overrideView, type StudioPlugin } from '@studio/plugins/types';
import {
  DEFAULT_PLUGIN_WORKSPACES,
  getActivePlugins,
  isPluginActive,
} from '@studio/plugins/workspace';
import type { FC } from 'react';

const Stub: FC = () => null;

const scopedPlugin = (workspaces?: StudioPlugin['workspaces']): StudioPlugin => ({
  id: 'scoped',
  name: 'scoped',
  workspaces,
  contributions: [
    contribute({
      slot: 'experiments.group.afterSearch',
      id: 'scoped:chart',
      render: Stub,
    }),
  ],
  viewOverrides: [],
});

const traceDetailPlugins = (): StudioPlugin[] => [
  {
    id: 'intake-trace-detail',
    name: 'intake-trace-detail',
    workspaces: ['default'],
    contributions: [],
    viewOverrides: [
      overrideView({
        viewId: 'intake.trace.detail',
        id: 'intake-trace-detail:view',
        render: Stub,
      }),
    ],
  },
  {
    id: 'intake-trace-detail-agent00',
    name: 'intake-trace-detail-agent00',
    workspaces: ['agent00'],
    contributions: [],
    viewOverrides: [
      overrideView({
        viewId: 'intake.trace.detail',
        id: 'intake-trace-detail-agent00:view',
        render: Stub,
      }),
    ],
  },
];

describe('isPluginActive', () => {
  it('defaults to the default workspace when workspaces is omitted', () => {
    const plugin = scopedPlugin();

    expect(isPluginActive(plugin, 'default')).toBe(true);
    expect(isPluginActive(plugin, 'rrhyne')).toBe(false);
  });

  it('uses DEFAULT_PLUGIN_WORKSPACES as the implicit scope', () => {
    expect(DEFAULT_PLUGIN_WORKSPACES).toEqual(['default']);
  });

  it('honors an explicit workspace list', () => {
    const plugin = scopedPlugin(['default', 'rrhyne']);

    expect(isPluginActive(plugin, 'default')).toBe(true);
    expect(isPluginActive(plugin, 'rrhyne')).toBe(true);
    expect(isPluginActive(plugin, 'team-a')).toBe(false);
  });

  it('activates in every workspace when scope is all', () => {
    const plugin = scopedPlugin('all');

    expect(isPluginActive(plugin, 'default')).toBe(true);
    expect(isPluginActive(plugin, 'rrhyne')).toBe(true);
  });
});

describe('getActivePlugins', () => {
  it('filters manifest plugins by workspace', () => {
    const plugins = [scopedPlugin(['default']), scopedPlugin(['rrhyne'])];

    expect(getActivePlugins(plugins, 'default').map((plugin) => plugin.id)).toEqual(['scoped']);
    expect(getActivePlugins(plugins, 'rrhyne')).toHaveLength(1);
    expect(getActivePlugins(plugins, 'team-a')).toHaveLength(0);
  });
});

describe('registry workspace filtering', () => {
  it('indexes slot contributions only for active workspaces', () => {
    const plugins = [
      scopedPlugin(['default']),
      {
        id: 'insights',
        name: 'insights',
        workspaces: ['default'],
        contributions: [
          contribute({
            slot: 'experiments.group.afterSearch',
            id: 'experiment-insights:cost-latency',
            render: Stub,
          }),
        ],
      },
    ];

    const defaultSlots = buildSlotIndex(getActivePlugins(plugins, 'default')).get(
      'experiments.group.afterSearch'
    );
    expect(defaultSlots?.some((c) => c.id === 'experiment-insights:cost-latency')).toBe(true);
    expect(
      buildSlotIndex(getActivePlugins(plugins, 'rrhyne')).get('experiments.group.afterSearch')
    ).toBeUndefined();
  });

  it('indexes view overrides only for active workspaces', () => {
    const plugins = traceDetailPlugins();
    const defaultViews = buildViewIndex(getActivePlugins(plugins, 'default'));
    const agentViews = buildViewIndex(getActivePlugins(plugins, 'agent00'));

    expect(defaultViews.get('intake.trace.detail')?.id).toBe('intake-trace-detail:view');
    expect(agentViews.get('intake.trace.detail')?.id).toBe('intake-trace-detail-agent00:view');
    expect(buildViewIndex(getActivePlugins(plugins, 'rrhyne')).get('intake.trace.detail')).toBeUndefined();
  });

  it('scopes intake trace detail plugins by workspace', () => {
    const [defaultPlugin, agentPlugin] = traceDetailPlugins();
    expect(defaultPlugin.workspaces).toEqual(['default']);
    expect(agentPlugin.workspaces).toEqual(['agent00']);
  });
});
