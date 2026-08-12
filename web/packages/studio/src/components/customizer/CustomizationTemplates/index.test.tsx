// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DEFAULT_WORKSPACE } from '@nemo/common/src/models/constants';
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

const HF_ROWS_URL = 'https://datasets-server.huggingface.co/rows';

/**
 * A BIRD-SQL row — the shape every shipped template's converter reads, so these tests
 * hold whichever template renders first. Extend this if a template adds a new source.
 */
const HF_ROW = {
  schema: 'CREATE TABLE t (id INT);',
  question: 'q',
  evidence: 'hint',
  SQL: 'SELECT 1',
};

const hfRowsHandler = http.get(HF_ROWS_URL, ({ request }) => {
  const length = Number(new URL(request.url).searchParams.get('length') ?? '0');
  return HttpResponse.json({
    rows: Array.from({ length }, () => ({ row: HF_ROW })),
  });
});

describe('CustomizationTemplates', () => {
  let navigate: Mock;

  beforeEach(() => {
    navigate = vi.fn();
    mockUseNavigate(navigate);
    mockUseParams({ [ROUTE_PARAMS.workspace]: DEFAULT_WORKSPACE });
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
    const gatedCount = CUSTOMIZATION_TEMPLATES.filter((t) =>
      t.models.some((m) => m.requiresHfToken)
    ).length;
    // queryAll, not getAll: no shipped template is gated today, and getAllByText throws
    // on zero matches rather than returning an empty list.
    expect(screen.queryAllByText('HF token')).toHaveLength(gatedCount);
  });

  it('provisions the model + dataset and navigates to the pre-filled form on "Use Template"', async () => {
    const user = userEvent.setup();
    render(
      <TestProviders>
        <CustomizationTemplates />
      </TestProviders>
    );

    await user.click(screen.getAllByRole('button', { name: 'Use Template' })[0]);

    await waitFor(
      () =>
        expect(navigate).toHaveBeenCalledWith(
          getNewCustomizationJobRoute(DEFAULT_WORKSPACE),
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
    server.use(http.get(HF_ROWS_URL, () => HttpResponse.json({ error: 'boom' }, { status: 500 })));
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
