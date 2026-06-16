/*
 * SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 *
 * NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
 * property and proprietary rights in and to this material, related
 * documentation and any modifications thereto. Any use, reproduction,
 * disclosure or distribution of this material and related documentation
 * without an express license agreement from NVIDIA CORPORATION or
 * its affiliates is strictly prohibited.
 */

import type { GuardrailConfig } from '@nemo/sdk/generated/platform/schema';
import { GuardrailsDetailPanel } from '@studio/routes/guardrails/GuardrailsDetailPanel';
import { render, screen } from '@studio/tests/util/render';
import userEvent from '@testing-library/user-event';

const mockConfig: GuardrailConfig = {
  id: 'cfg-1',
  entity_id: 'cfg-1',
  parent: 'ws-default',
  name: 'pii-filter',
  workspace: 'default',
  description: 'Blocks PII in user inputs and outputs',
  created_at: '2026-04-12T10:00:00.000Z',
  created_by: 'user@example.com',
  updated_at: '2026-04-12T10:00:00.000Z',
  updated_by: 'user@example.com',
  data: {
    models: [{ type: 'main', engine: 'openai', model: 'gpt-4' }],
    rails: {
      input: { flows: ['check pii'] },
      output: { flows: ['mask pii output'] },
    },
  },
};

describe('GuardrailsDetailPanel', () => {
  it('renders the config name as heading when open', async () => {
    render(
      <GuardrailsDetailPanel open config={mockConfig} onClose={vi.fn()} onRequestDelete={vi.fn()} />
    );
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('pii-filter')).toBeInTheDocument();
  });

  it('renders description, model count, and rail count', async () => {
    render(
      <GuardrailsDetailPanel open config={mockConfig} onClose={vi.fn()} onRequestDelete={vi.fn()} />
    );
    await screen.findByRole('dialog');
    expect(screen.getByText('Blocks PII in user inputs and outputs')).toBeInTheDocument();
    expect(screen.getByText('1')).toBeInTheDocument(); // 1 model
    expect(screen.getByText('2')).toBeInTheDocument(); // 2 rail flows
  });

  it('calls onRequestDelete with the config when Delete is clicked', async () => {
    const onRequestDelete = vi.fn();
    render(
      <GuardrailsDetailPanel
        open
        config={mockConfig}
        onClose={vi.fn()}
        onRequestDelete={onRequestDelete}
      />
    );
    await screen.findByRole('dialog');
    screen.getByRole('button', { name: /delete/i }).click();
    expect(onRequestDelete).toHaveBeenCalledWith(mockConfig);
  });

  it('calls onClose when the panel close button is clicked', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(
      <GuardrailsDetailPanel open config={mockConfig} onClose={onClose} onRequestDelete={vi.fn()} />
    );
    await screen.findByRole('dialog');
    // SidePanel close button has accessible label from KUI
    const closeButton = screen.getByRole('button', { name: /close/i });
    await user.click(closeButton);
    expect(onClose).toHaveBeenCalled();
  });

  it('does not show content when closed', () => {
    render(
      <GuardrailsDetailPanel
        open={false}
        config={mockConfig}
        onClose={vi.fn()}
        onRequestDelete={vi.fn()}
      />
    );
    // When closed, the config content should not be visible
    expect(screen.queryByText('pii-filter')).not.toBeInTheDocument();
  });
});
