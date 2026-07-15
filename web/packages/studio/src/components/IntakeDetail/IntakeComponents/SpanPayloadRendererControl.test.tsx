// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { IntakeAccordion } from '@nemo/common/src/components/IntakeAccordion';
import {
  SpanPayloadRendererControl,
  SpanPayloadViewMode,
} from '@studio/components/IntakeDetail/IntakeComponents/SpanPayloadRendererControl';
import { renderRoute, screen } from '@studio/tests/util/render';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';

describe('SpanPayloadRendererControl', () => {
  it('exposes accessible chat, raw, Markdown, and JSON options', async () => {
    const user = userEvent.setup();
    const onValueChange = vi.fn();
    renderRoute(
      <SpanPayloadRendererControl
        sectionLabel="Input"
        value={SpanPayloadViewMode.raw}
        onValueChange={onValueChange}
      />
    );

    expect(screen.getByRole('radiogroup', { name: 'Input rendering style' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Chat' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'raw' })).toBeChecked();
    expect(screen.getByRole('radio', { name: 'md' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'json' })).toBeInTheDocument();

    await user.click(screen.getByRole('radio', { name: 'json' }));

    expect(onValueChange).toHaveBeenCalledWith(SpanPayloadViewMode.json);
  });

  it('changes modes without toggling the surrounding accordion', async () => {
    const user = userEvent.setup();
    const onModeChange = vi.fn();

    const Harness = () => {
      const [viewMode, setViewMode] = useState<SpanPayloadViewMode>(SpanPayloadViewMode.raw);
      const handleModeChange = (nextMode: SpanPayloadViewMode): void => {
        onModeChange(nextMode);
        setViewMode(nextMode);
      };
      return (
        <IntakeAccordion
          defaultValue={['input']}
          items={[
            {
              value: 'input',
              slotLabel: 'Input',
              slotEnd: (
                <SpanPayloadRendererControl
                  sectionLabel="Input"
                  value={viewMode}
                  onValueChange={handleModeChange}
                />
              ),
              slotContent: <p>Visible input payload</p>,
            },
          ]}
        />
      );
    };

    renderRoute(<Harness />);

    const jsonOption = screen.getByRole('radio', { name: 'json' });
    expect(screen.getByText('Visible input payload')).toBeVisible();

    await user.click(jsonOption);

    expect(onModeChange).toHaveBeenCalledWith(SpanPayloadViewMode.json);
    expect(jsonOption).toBeChecked();
    expect(screen.getByText('Visible input payload')).toBeVisible();

    const markdownOption = screen.getByRole('radio', { name: 'md' });
    markdownOption.focus();
    await user.keyboard(' ');

    expect(markdownOption).toBeChecked();
    expect(screen.getByText('Visible input payload')).toBeVisible();
  });
});
