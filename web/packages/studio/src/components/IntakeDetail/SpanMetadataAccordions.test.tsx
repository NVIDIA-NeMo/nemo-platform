// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DEFAULT_WORKSPACE } from '@nemo/common/src/models/constants';
import { SpanMetadataAccordions } from '@studio/components/IntakeDetail/SpanMetadataAccordions';
import { mockSpanById } from '@studio/mocks/intake/telemetry';
import { renderRoute, screen, within } from '@studio/tests/util/render';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';

describe('SpanMetadataAccordions payload renderers', () => {
  it('keeps Input and Output renderer selection independent without collapsing sections', async () => {
    const user = userEvent.setup();
    const span = {
      ...mockSpanById('span-root-001')!,
      input: '{"prompt":"hello"}',
      output: '# Output heading',
    };

    renderRoute(<SpanMetadataAccordions span={span} workspace={DEFAULT_WORKSPACE} />);

    const inputRenderer = screen.getByRole('radiogroup', { name: 'Input rendering style' });
    const outputRenderer = screen.getByRole('radiogroup', { name: 'Output rendering style' });
    const inputJson = within(inputRenderer).getByRole('radio', { name: 'json' });
    const inputRaw = within(inputRenderer).getByRole('radio', { name: 'raw' });
    const outputMarkdown = within(outputRenderer).getByRole('radio', { name: 'md' });
    const outputRaw = within(outputRenderer).getByRole('radio', { name: 'raw' });

    expect(inputRaw).toBeChecked();
    expect(outputRaw).toBeChecked();
    expect(screen.getByText('{"prompt":"hello"}')).toBeVisible();
    expect(screen.getByText('# Output heading')).toBeVisible();

    await user.click(inputJson);

    expect(inputJson).toBeChecked();
    expect(outputRaw).toBeChecked();
    expect(screen.getByText('# Output heading')).toBeVisible();

    await user.click(outputMarkdown);

    expect(inputJson).toBeChecked();
    expect(outputMarkdown).toBeChecked();
    expect(screen.getByRole('heading', { name: 'Output heading' })).toBeVisible();
  });

  it('resets payload rendering modes when the selected span changes', async () => {
    const user = userEvent.setup();
    const firstSpan = {
      ...mockSpanById('span-root-001')!,
      input: '{"span":"first"}',
    };
    const secondSpan = {
      ...firstSpan,
      span_id: 'span-second',
      input: '{"span":"second"}',
    };

    const Harness = () => {
      const [span, setSpan] = useState(firstSpan);
      return (
        <>
          <button type="button" onClick={() => setSpan(firstSpan)}>
            Select first span
          </button>
          <button type="button" onClick={() => setSpan(secondSpan)}>
            Select second span
          </button>
          <SpanMetadataAccordions span={span} workspace={DEFAULT_WORKSPACE} />
        </>
      );
    };

    renderRoute(<Harness />);
    const inputRenderer = screen.getByRole('radiogroup', { name: 'Input rendering style' });

    await user.click(within(inputRenderer).getByRole('radio', { name: 'json' }));
    expect(within(inputRenderer).getByRole('radio', { name: 'json' })).toBeChecked();

    await user.click(screen.getByRole('button', { name: 'Select second span' }));

    expect(within(inputRenderer).getByRole('radio', { name: 'raw' })).toBeChecked();
    expect(screen.getByText('{"span":"second"}')).toBeVisible();

    await user.click(screen.getByRole('button', { name: 'Select first span' }));

    expect(within(inputRenderer).getByRole('radio', { name: 'raw' })).toBeChecked();
    expect(screen.getByText('{"span":"first"}')).toBeVisible();
  });
});
