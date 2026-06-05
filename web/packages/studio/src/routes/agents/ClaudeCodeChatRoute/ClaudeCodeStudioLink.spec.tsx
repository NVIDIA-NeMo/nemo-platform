// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  ClaudeCodeStudioLink,
  getStudioInternalLinkTarget,
} from '@studio/routes/agents/ClaudeCodeChatRoute/ClaudeCodeStudioLink';
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
