// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { WorkspaceSideNav } from '@studio/routes/WorkspaceLayout/WorkspaceSideNav';
import { renderRoute, screen } from '@studio/tests/util/render';

vi.hoisted(() => {
  vi.stubEnv('VITE_FF_OPTIMIZER_ENABLED', 'false');
});

describe('WorkspaceSideNav', () => {
  it('labels the intake navigation link as Traces', () => {
    renderRoute(<WorkspaceSideNav />, {
      history: '/workspaces/test-workspace/intake/traces',
      routes: [
        {
          path: '/workspaces/:workspace/*',
          element: <WorkspaceSideNav />,
        },
      ],
    });

    expect(screen.getByRole('link', { name: 'Traces' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Annotation' })).not.toBeInTheDocument();
  });

  it('omits Optimizer navigation when Optimizer is disabled', () => {
    renderRoute(<WorkspaceSideNav />, {
      history: '/workspaces/test-workspace/dashboard',
      routes: [
        {
          path: '/workspaces/:workspace/*',
          element: <WorkspaceSideNav />,
        },
      ],
    });

    expect(screen.queryByRole('link', { name: 'Insights' })).not.toBeInTheDocument();
  });
});
