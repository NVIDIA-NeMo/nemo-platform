// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { IntakeLayout } from '@studio/routes/IntakeLayout';
import { renderRoute, screen, waitFor } from '@studio/tests/util/render';

const { mockUseBreadcrumbs } = vi.hoisted(() => ({
  mockUseBreadcrumbs: vi.fn(),
}));

vi.mock('@studio/providers/breadcrumbs/useBreadcrumbs', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@studio/providers/breadcrumbs/useBreadcrumbs')>();
  return {
    ...actual,
    useBreadcrumbs: mockUseBreadcrumbs,
  };
});

describe('IntakeLayout', () => {
  it('uses Traces for the section heading, breadcrumb, and document title', async () => {
    renderRoute(undefined, {
      history: '/workspaces/default/intake/traces',
      routes: [
        {
          path: '/workspaces/:workspace/intake/:selectedTab',
          element: <IntakeLayout />,
        },
      ],
    });

    expect(screen.getByTestId('nv-page-header-heading')).toHaveTextContent('Traces');
    expect(mockUseBreadcrumbs).toHaveBeenCalledWith({
      items: [{ slotLabel: 'Traces' }],
    });
    await waitFor(() => expect(document.title).toBe('Traces - Studio'));
  });
});
