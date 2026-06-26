// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { AnnotationsPanel } from '@studio/components/IntakeDetail/IntakeComponents/AnnotationsPanel';
import { resetMockAnnotations } from '@studio/mocks/intake/telemetry';
import { renderRoute, screen, waitFor, within } from '@studio/tests/util/render';
import userEvent from '@testing-library/user-event';

const SPAN_ID = 'span-root-001';
const SESSION_ID = 'session-agent-run-001';

describe('AnnotationsPanel', () => {
  beforeEach(() => {
    resetMockAnnotations();
  });

  it('lists and creates span annotations through the generated client', async () => {
    const user = userEvent.setup();

    renderRoute(<AnnotationsPanel workspace="default" spanId={SPAN_ID} sessionId={SESSION_ID} />, {
      history: '/workspaces/default/intake/spans/span-root-001',
    });

    expect(
      await screen.findByText('Good final response, but verify policy citations.')
    ).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Negative/i }));
    expect(
      await screen.findByRole('article', { name: 'Negative feedback annotation' })
    ).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText('Add a note about this span.'), 'Needs review.');
    await user.click(screen.getByRole('button', { name: /Add Note/i }));

    expect(await screen.findByText('Needs review.')).toBeInTheDocument();
  });

  it('deletes span annotations through the generated client', async () => {
    const user = userEvent.setup();

    renderRoute(<AnnotationsPanel workspace="default" spanId={SPAN_ID} sessionId={SESSION_ID} />, {
      history: '/workspaces/default/intake/spans/span-root-001',
    });

    const note = await screen.findByRole('article', { name: 'Note annotation' });
    await user.click(within(note).getByRole('button', { name: /Delete/i }));

    await waitFor(() => {
      expect(
        screen.queryByText('Good final response, but verify policy citations.')
      ).not.toBeInTheDocument();
    });
  });
});
