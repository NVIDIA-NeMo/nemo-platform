// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ClaudeCodeStudioLink } from '@studio/routes/agents/ClaudeCodeChatRoute/ClaudeCodeStudioLink';
import { getStudioInternalLinkTarget } from '@studio/routes/agents/ClaudeCodeChatRoute/ClaudeCodeStudioLinkTarget';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

describe('ClaudeCodeStudioLink', () => {
  it('accepts same-origin Studio workspace paths', () => {
    expect(getStudioInternalLinkTarget('/workspaces/default/agents', 'https://studio.test')).toBe(
      '/workspaces/default/agents'
    );
    expect(
      getStudioInternalLinkTarget(
        'https://studio.test/workspaces/default/agents?status=ready#agent',
        'https://studio.test'
      )
    ).toBe('/workspaces/default/agents?status=ready#agent');
  });

  it('rejects external links', () => {
    expect(
      getStudioInternalLinkTarget('https://example.com/settings', 'https://studio.test')
    ).toBeUndefined();
  });

  it('internalizes absolute Studio links from other local origins', () => {
    expect(
      getStudioInternalLinkTarget(
        'http://localhost:8080/workspaces/danielleali/customizations',
        'http://ns.local.aire.nvidia.com:5173',
        'default'
      )
    ).toBe('/workspaces/default/customizations');
  });

  it('maps legacy Studio entry URLs to the current workspace dashboard', () => {
    expect(
      getStudioInternalLinkTarget(
        'http://localhost:8080/studio',
        'http://ns.local.aire.nvidia.com:5173',
        'default'
      )
    ).toBe('/workspaces/default/dashboard');
  });

  it('strips legacy Studio prefixes and rewrites stale workspaces', () => {
    expect(
      getStudioInternalLinkTarget(
        'http://localhost:8080/studio/workspaces/danielleali/agents/spanish-translator?tab=chat-playground',
        'http://ns.local.aire.nvidia.com:5173',
        'default'
      )
    ).toBe('/workspaces/default/agents/spanish-translator?tab=chat-playground');
  });

  it('canonicalizes generated evaluation results links to the registered route', () => {
    expect(
      getStudioInternalLinkTarget(
        '/workspaces/default/dashboard/evaluations/results',
        'https://studio.test'
      )
    ).toBe('/workspaces/default/evaluation/results');
    expect(
      getStudioInternalLinkTarget(
        'http://localhost:8080/workspaces/danielleali/dashboard/evaluation/results?status=complete',
        'http://ns.local.aire.nvidia.com:5173',
        'default'
      )
    ).toBe('/workspaces/default/evaluation/results?status=complete');
    expect(
      getStudioInternalLinkTarget(
        '/workspaces/default/evaluations/results#latest',
        'https://studio.test'
      )
    ).toBe('/workspaces/default/evaluation/results#latest');
  });

  it('renders accepted Studio paths as router links', () => {
    render(
      <MemoryRouter>
        <ClaudeCodeStudioLink href="/workspaces/default/agents">Agents</ClaudeCodeStudioLink>
      </MemoryRouter>
    );

    const link = screen.getByRole('link', { name: 'Agents' });

    expect(link).toHaveAttribute('href', '/workspaces/default/agents');
    expect(link).toHaveClass('inline-flex', 'rounded');
    expect(link.className).toContain('bg-[linear-gradient');
  });

  it('renders rejected paths as inert text', () => {
    render(
      <MemoryRouter>
        <ClaudeCodeStudioLink href="https://example.com">External</ClaudeCodeStudioLink>
      </MemoryRouter>
    );

    expect(screen.queryByRole('link', { name: 'External' })).not.toBeInTheDocument();
    expect(screen.getByText('External')).toBeInTheDocument();
  });
});
