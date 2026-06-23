// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { buildSlotIndex, buildViewIndex, collectPluginRoutes } from '@studio/plugins/registry';
import { contribute, overrideView, type StudioPlugin } from '@studio/plugins/types';
import type { FC } from 'react';

const Stub: FC = () => null;

const makePlugin = (id: string, contributions: StudioPlugin['contributions']): StudioPlugin => ({
  id,
  name: id,
  contributions,
});

describe('buildSlotIndex', () => {
  it('groups contributions by slot and orders them by `order` across plugins', () => {
    const plugins = [
      makePlugin('p1', [
        contribute({
          slot: 'experiments.group.afterSearch',
          id: 'p1:later',
          order: 2,
          render: Stub,
        }),
      ]),
      makePlugin('p2', [
        contribute({
          slot: 'experiments.group.afterSearch',
          id: 'p2:earlier',
          order: 1,
          render: Stub,
        }),
      ]),
    ];

    const ids = (buildSlotIndex(plugins).get('experiments.group.afterSearch') ?? []).map(
      (c) => c.id
    );

    expect(ids).toEqual(['p2:earlier', 'p1:later']);
  });

  it('defaults `order` to 0 and keeps manifest order for ties', () => {
    const plugins = [
      makePlugin('p1', [
        contribute({ slot: 'experiments.group.afterSearch', id: 'p1:a', render: Stub }),
        contribute({ slot: 'experiments.group.afterSearch', id: 'p1:b', render: Stub }),
      ]),
    ];

    const ids = (buildSlotIndex(plugins).get('experiments.group.afterSearch') ?? []).map(
      (c) => c.id
    );

    expect(ids).toEqual(['p1:a', 'p1:b']);
  });

  it('returns no entry for a slot no plugin targets', () => {
    expect(buildSlotIndex([]).get('experiments.group.afterSearch')).toBeUndefined();
  });
});

describe('collectPluginRoutes', () => {
  it('flattens plugin routes into RouteObjects', () => {
    const plugins: StudioPlugin[] = [
      {
        id: 'demo',
        name: 'demo',
        contributions: [],
        routes: [{ id: 'demo:report', path: 'experiment/:name/errors', render: Stub }],
      },
    ];

    const routes = collectPluginRoutes(plugins);
    const reportRoute = routes.find((route) => route.path === 'experiment/:name/errors');

    expect(reportRoute).toBeDefined();
    expect(reportRoute?.element).toBeDefined();
  });
});

describe('buildViewIndex', () => {
  it('picks the lowest-order override when multiple plugins target the same view', () => {
    const plugins = [
      {
        id: 'p1',
        name: 'p1',
        contributions: [],
        viewOverrides: [
          overrideView({
            viewId: 'intake.trace.detail',
            id: 'p1:override',
            order: 2,
            render: Stub,
          }),
        ],
      },
      {
        id: 'p2',
        name: 'p2',
        contributions: [],
        viewOverrides: [
          overrideView({
            viewId: 'intake.trace.detail',
            id: 'p2:override',
            order: 1,
            render: Stub,
          }),
        ],
      },
    ];

    expect(buildViewIndex(plugins).get('intake.trace.detail')?.id).toBe('p2:override');
  });
});
