// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ModelSelectBlockingInput } from '@studio/components/agents/AgentBlockingInput/ModelSelectBlockingInput';
import type { AgentBlockingInputSubmission } from '@studio/components/agents/AgentBlockingInput/types';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('@studio/components/evaluation/JudgeModelSelect', async () => {
  const { useFormContext } =
    await vi.importActual<typeof import('react-hook-form')>('react-hook-form');

  return {
    JudgeModelSelect: ({ formFieldName }: { readonly formFieldName: string }) => {
      const form = useFormContext();
      const selectedModel = form.watch(formFieldName);

      return (
        <>
          <span data-testid="selected-model">{selectedModel}</span>
          <button type="button" onClick={() => form.setValue(formFieldName, 'stale-model')}>
            Select stale model
          </button>
        </>
      );
    },
  };
});

describe('ModelSelectBlockingInput', () => {
  it('resets the selected model when the blocking request changes', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn<(submission: AgentBlockingInputSubmission) => void>();
    const { rerender } = render(
      <ModelSelectBlockingInput
        input={{ default_model: 'first-model' }}
        request={{ id: 'request-1', title: 'Select model' }}
        onSubmit={onSubmit}
      />
    );

    expect(screen.getByTestId('selected-model')).toHaveTextContent('first-model');

    await user.click(screen.getByRole('button', { name: 'Select stale model' }));
    expect(screen.getByTestId('selected-model')).toHaveTextContent('stale-model');

    rerender(
      <ModelSelectBlockingInput
        input={{ default_model: 'second-model' }}
        request={{ id: 'request-2', title: 'Select model' }}
        onSubmit={onSubmit}
      />
    );

    await waitFor(() =>
      expect(screen.getByTestId('selected-model')).toHaveTextContent('second-model')
    );
  });
});
