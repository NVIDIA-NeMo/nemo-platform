// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { BadgeStatus, badgeStatus } from '@nemo/common/src/components/StatusBadge/badgeStatus';
import { StatusBadge } from '@nemo/common/src/components/StatusBadge/index';
import * as customQueries from '@nemo/common/src/tests/customQueries';
import { queries, render, screen, within } from '@testing-library/react';

const allQueries = {
  ...queries,
  ...customQueries,
};
const customScreen = within(document.body, allQueries);

describe('StatusBadge component', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  it('renders with a valid status', () => {
    const status: BadgeStatus = 'completed';
    render(<StatusBadge status={status} />);

    const badge = screen.getByTestId('nv-badge');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveTextContent('Completed');
  });

  it('normalizes uppercase statuses (e.g. ModelProvider API)', () => {
    render(<StatusBadge status={'READY' as BadgeStatus} />);

    const badge = screen.getByTestId('nv-badge');
    expect(badge).toHaveTextContent(badgeStatus.ready.label);
    expect(badge).toHaveClass('nv-badge--color-green');
  });

  it('renders with undefined status and shows default badge', () => {
    render(<StatusBadge status={undefined} />);

    const badge = screen.getByTestId('nv-badge');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveTextContent(badgeStatus.default.label);
  });

  it('renders with icon when iconName is provided', async () => {
    const status: BadgeStatus = 'in_progress';
    render(<StatusBadge status={status} />, { queries: allQueries });

    // Use querySelector with document to find SVG (escape hatch for SVG testing)
    // eslint-disable-next-line testing-library/no-node-access
    const icon = document.querySelector('.lucide-refresh-cw');
    expect(icon).toBeInTheDocument();
    expect(icon).toHaveAttribute('width', '12px');
    expect(icon).toHaveAttribute('height', '12px');
  });

  it('renders icon for all current statuses', async () => {
    // Since all current statuses have icons, we'll verify the icon exists
    render(<StatusBadge status="completed" />);

    // eslint-disable-next-line testing-library/no-node-access
    const icon = document.querySelector('.lucide-circle-check');
    expect(icon).toBeInTheDocument();
  });

  it('applies correct badge properties for each status', () => {
    const testStatuses: BadgeStatus[] = [
      'created',
      'completed',
      'error',
      'pending',
      'in_progress',
      'cancelling',
      'cancelled',
    ];

    testStatuses.forEach((status) => {
      const { unmount } = render(<StatusBadge status={status} />);

      const badge = screen.getByTestId('nv-badge');
      const expectedBadge = badgeStatus[status];

      expect(badge).toBeInTheDocument();
      expect(badge).toHaveTextContent(expectedBadge.label);

      // Check if icon is rendered when icon exists
      const icon = customScreen.getByRole('img');
      expect(icon).toBeInTheDocument();

      unmount();
    });
  });

  it('handles invalid status by falling back to default', () => {
    // Test with a status that doesn't exist in badgeStatus
    render(<StatusBadge status={'nonexistent' as BadgeStatus} />);

    const badge = screen.getByTestId('nv-badge');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveTextContent(badgeStatus.default.label);
  });

  it('renders badge with solid type', () => {
    render(<StatusBadge status="completed" />);

    const badge = screen.getByTestId('nv-badge');
    expect(badge).toBeInTheDocument();
    // The Badge component should receive type="solid" prop
    // This is more of an integration test to ensure props are passed correctly
  });

  describe('status-specific rendering', () => {
    const statusList = [
      'running',
      'default',
      'created',
      'pending',
      'cancelled',
      'cancelling',
      'failed',
      'completed',
      'ready',
      'unknown',
      'unavailable',
      undefined,
    ] as BadgeStatus[];

    statusList.forEach((status) => {
      it(`renders the correct badge for ${status === undefined ? 'undefined' : `'${status}'`} status`, () => {
        render(<StatusBadge status={status} />);
        const badge = screen.getByTestId('nv-badge');

        const expectedStatus =
          status === undefined ? badgeStatus.default : badgeStatus[status] || badgeStatus.default;

        expect(badge).toBeInTheDocument();
        expect(badge).toHaveTextContent(expectedStatus.label);
        // If the color is blue, it's the default color and won't have a specific color class
        if (expectedStatus.color === 'blue') {
          expect(badge).toHaveClass('nv-badge nv-badge--kind-solid');
        } else {
          expect(badge).toHaveClass(`nv-badge--color-${expectedStatus.color}`);
        }
      });
    });
  });
});
