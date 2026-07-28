// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { CustomizationTemplates } from '@studio/components/customizer/CustomizationTemplates';
import { CUSTOMIZATION_TEMPLATES } from '@studio/constants/customizationTemplates';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { server } from '@studio/mocks/node';
import { getNewCustomizationJobRoute } from '@studio/routes/utils';
import { mockUseNavigate, mockUseParams } from '@studio/tests/util/mockUseParams';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import type { Mock } from 'vitest';

const WORKSPACE = 'default';

/** Returns `length` valid SQuAD rows so the converter yields enough train + validation data. */
const hfRowsHandler = http.get('https://datasets-server.huggingface.co/rows', ({ request }) => {
  const length = Number(new URL(request.url).searchParams.get('length') ?? '0');
  return HttpResponse.json({
    rows: Array.from({ length }, () => ({
      row: { context: 'ctx', question: 'q', answers: { text: ['a'] } },
    })),
  });
});

describe('CustomizationTemplates', () => {
  let navigate: Mock;

  beforeEach(() => {
    navigate = vi.fn();
    mockUseNavigate(navigate);
    mockUseParams({ [ROUTE_PARAMS.workspace]: WORKSPACE });
    server.use(hfRowsHandler);
  });

  it('renders a card for every template', () => {
    render(
      <TestProviders>
        <CustomizationTemplates />
      </TestProviders>
    );
    for (const template of CUSTOMIZATION_TEMPLATES) {
      expect(screen.getByText(template.title)).toBeInTheDocument();
    }
    // Gated templates surface an "HF token" badge; open ones do not.
    const gatedCount = CUSTOMIZATION_TEMPLATES.filter((t) =>
      t.models.some((m) => m.requiresHfToken)
    ).length;
    expect(screen.getAllByText('HF token')).toHaveLength(gatedCount);
  });

  it('provisions the model + dataset and navigates to the pre-filled form on "Use Template"', async () => {
    const user = userEvent.setup();
    render(
      <TestProviders>
        <CustomizationTemplates />
      </TestProviders>
    );

    // First card is the LoRA (no HF token) template.
    await user.click(screen.getAllByRole('button', { name: 'Use Template' })[0]);

    await waitFor(
      () =>
        expect(navigate).toHaveBeenCalledWith(
          getNewCustomizationJobRoute(WORKSPACE),
          expect.objectContaining({
            state: expect.objectContaining({
              initialValues: expect.objectContaining({ backend: 'automodel' }),
            }),
          })
        ),
      { timeout: 10_000 }
    );
  });

  it('surfaces an error and does not navigate when dataset fetch fails', async () => {
    server.use(
      http.get('https://datasets-server.huggingface.co/rows', () =>
        HttpResponse.json({ error: 'boom' }, { status: 500 })
      )
    );
    const user = userEvent.setup();
    render(
      <TestProviders>
        <CustomizationTemplates />
      </TestProviders>
    );

    await user.click(screen.getAllByRole('button', { name: 'Use Template' })[0]);

    expect(await screen.findByText(/Failed to set up template/i)).toBeInTheDocument();
    expect(navigate).not.toHaveBeenCalled();
  });
});
