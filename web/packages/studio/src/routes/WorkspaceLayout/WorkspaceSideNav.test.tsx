// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { WorkspaceSideNav } from '@studio/routes/WorkspaceLayout/WorkspaceSideNav';
import { renderRoute, screen } from '@studio/tests/util/render';
import userEvent from '@testing-library/user-event';

vi.hoisted(() => {
  vi.stubEnv('VITE_FF_OPTIMIZER_ENABLED', 'false');
  vi.stubEnv('VITE_FF_CUSTOMIZER_ENABLED', 'true');
});

/** A parent row's label is a link; its chevron is a separate disclosure button. */
const disclosure = (label: string) => screen.getByRole('button', { name: new RegExp(label, 'i') });

const renderSideNav = (history = '/workspaces/test-workspace/dashboard') =>
  renderRoute(<WorkspaceSideNav />, {
    history,
    routes: [
      {
        path: '/workspaces/:workspace/*',
        element: <WorkspaceSideNav />,
      },
    ],
  });

describe('WorkspaceSideNav', () => {
  it('links to the traces view by default', () => {
    renderSideNav();

    expect(screen.getByRole('link', { name: 'Traces' })).toHaveAttribute(
      'href',
      '/workspaces/test-workspace/intake/traces'
    );
    expect(screen.queryByRole('link', { name: /annotations?/i })).not.toBeInTheDocument();
  });

  it('omits Optimizer navigation when Optimizer is disabled', () => {
    renderSideNav();

    expect(screen.queryByRole('link', { name: 'Insights' })).not.toBeInTheDocument();
  });

  it('renders the six RFC sections', () => {
    renderSideNav();

    for (const section of ['Observability', 'Components', 'Data', 'Governance', 'System']) {
      expect(screen.getByText(section)).toBeInTheDocument();
    }
    // Superseded group headings
    expect(screen.queryByText('Safety')).not.toBeInTheDocument();
    expect(screen.queryByText('Evaluate')).not.toBeInTheDocument();
  });

  it('links the Agents and Models parents to their own entity list pages', () => {
    renderSideNav();

    expect(screen.getByRole('link', { name: 'Agents' })).toHaveAttribute(
      'href',
      '/workspaces/test-workspace/agents'
    );
    expect(screen.getByRole('link', { name: 'Models' })).toHaveAttribute(
      'href',
      '/workspaces/test-workspace/base-models'
    );
    expect(screen.queryByRole('link', { name: 'Base Models' })).not.toBeInTheDocument();
  });

  it('expands and collapses a parent from the chevron alone', async () => {
    const user = userEvent.setup();
    renderSideNav('/workspaces/test-workspace/agents/monitor');

    expect(disclosure('Agents')).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('link', { name: 'Monitor' })).toHaveAttribute(
      'href',
      '/workspaces/test-workspace/agents/monitor'
    );

    await user.click(disclosure('Agents'));
    expect(disclosure('Agents')).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('link', { name: 'Monitor' })).not.toBeInTheDocument();
    // Collapsing the sub-list leaves the parent's own link intact.
    expect(screen.getByRole('link', { name: 'Agents' })).toBeInTheDocument();
  });

  it('renders the customization screen as Fine-tune under Models', () => {
    renderSideNav('/workspaces/test-workspace/customizations');

    expect(screen.getByRole('link', { name: 'Fine-tune' })).toHaveAttribute(
      'href',
      '/workspaces/test-workspace/customizations'
    );
    expect(screen.queryByText('Custom Models')).not.toBeInTheDocument();
  });

  it('expands only the parent owning the current nested route', () => {
    renderSideNav('/workspaces/test-workspace/agents/monitor');

    expect(disclosure('Agents')).toHaveAttribute('aria-expanded', 'true');
    expect(disclosure('Models')).toHaveAttribute('aria-expanded', 'false');
  });
});
