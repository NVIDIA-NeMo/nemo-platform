// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RailsConfig } from '@nemo/sdk/generated/platform/schema';
import { GuardrailConfigurationPanel } from '@studio/routes/guardrails/GuardrailConfigTab/GuardrailConfigurationPanel';
import {
  type GuardrailFormValues,
  mapConfigToForm,
} from '@studio/routes/guardrails/GuardrailForm/formModel';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { FC } from 'react';
import { FormProvider, useForm } from 'react-hook-form';

const mountPanel = (data?: RailsConfig) => {
  const seen: { values?: GuardrailFormValues } = {};

  const Harness: FC = () => {
    const form = useForm<GuardrailFormValues>({ defaultValues: mapConfigToForm(data) });
    seen.values = form.watch();
    return (
      <TestProviders>
        <FormProvider {...form}>
          <GuardrailConfigurationPanel />
        </FormProvider>
      </TestProviders>
    );
  };

  render(<Harness />);
  return seen;
};

describe('GuardrailConfigurationPanel', () => {
  it('lists the configurable rails with the stages they run at', () => {
    mountPanel();

    expect(screen.getByText('Guardrails')).toBeInTheDocument();
    expect(screen.getByText('Self Checks')).toBeInTheDocument();
    expect(screen.getByText('Input')).toBeInTheDocument();
    expect(screen.getByText('Output')).toBeInTheDocument();
  });

  it('reflects a config that already has the rail switched on', () => {
    const seen = mountPanel({
      rails: { input: { flows: ['self check input'] } },
      prompts: [{ task: 'self_check_input', content: 'Block?' }],
    });

    expect(screen.getByRole('switch', { name: 'Self Checks' })).toBeChecked();
    expect(seen.values?.config.rails?.input?.flows).toEqual(['self check input']);
  });

  it('switching a rail on writes its flows and prompts together', async () => {
    const user = userEvent.setup();
    const seen = mountPanel();

    await user.click(screen.getByRole('switch', { name: 'Self Checks' }));

    await waitFor(() => {
      expect(seen.values?.config.rails?.input?.flows).toEqual(['self check input']);
    });
    // The prompt is the check — a flow without one is a config the engine rejects.
    expect(seen.values?.config.prompts?.map((prompt) => prompt.task)).toEqual([
      'self_check_input',
      'self_check_output',
    ]);
  });

  it('offers to discard settings only once a rail is off and has some', async () => {
    const user = userEvent.setup();
    mountPanel();

    expect(
      screen.queryByRole('button', { name: /Discard saved Self Checks settings/ })
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole('switch', { name: 'Self Checks' }));
    await user.click(screen.getByRole('switch', { name: 'Self Checks' }));

    expect(
      await screen.findByRole('button', { name: /Discard saved Self Checks settings/ })
    ).toBeInTheDocument();
  });

  it('discarding removes the prompts that switching off kept', async () => {
    const user = userEvent.setup();
    const seen = mountPanel();

    await user.click(screen.getByRole('switch', { name: 'Self Checks' }));
    await user.click(screen.getByRole('switch', { name: 'Self Checks' }));
    await user.click(
      await screen.findByRole('button', { name: /Discard saved Self Checks settings/ })
    );

    await waitFor(() => {
      expect(seen.values?.config.prompts).toBeUndefined();
    });
  });
});

describe('rail settings panel', () => {
  it('opens on the gear and shows a prompt per stage, with no model picker', async () => {
    const user = userEvent.setup();
    mountPanel();

    await user.click(screen.getByRole('button', { name: 'Configure Self Checks' }));

    expect(await screen.findByText('Self Checks Rail')).toBeInTheDocument();
    expect(screen.getByText('Input Prompt')).toBeInTheDocument();
    expect(screen.getByText('Output Prompt')).toBeInTheDocument();
    // Self check runs on the request's own model, so offering a picker would be wrong.
    expect(screen.queryByLabelText('Model')).not.toBeInTheDocument();
  });

  it('applies edits only on Apply', async () => {
    const user = userEvent.setup();
    const seen = mountPanel();

    await user.click(screen.getByRole('button', { name: 'Configure Self Checks' }));
    const prompt = await screen.findByLabelText('Input Prompt template');
    await user.clear(prompt);
    await user.type(prompt, 'Only block questions about pricing.');

    // Still untouched while the draft is open.
    expect(seen.values?.config.prompts).toBeUndefined();

    await user.click(screen.getByRole('button', { name: 'Apply' }));

    await waitFor(() => {
      expect(seen.values?.config.prompts?.[0]?.content).toBe('Only block questions about pricing.');
    });
  });

  it('discards edits on Cancel', async () => {
    const user = userEvent.setup();
    const seen = mountPanel();

    await user.click(screen.getByRole('button', { name: 'Configure Self Checks' }));
    const prompt = await screen.findByLabelText('Input Prompt template');
    await user.clear(prompt);
    await user.type(prompt, 'Throw this away.');
    await user.click(screen.getByRole('button', { name: 'Cancel' }));

    await waitFor(() => {
      expect(screen.queryByText('Self Checks Rail')).not.toBeInTheDocument();
    });
    expect(seen.values?.config.prompts).toBeUndefined();
  });

  it('inserts a template variable at the caret', async () => {
    const user = userEvent.setup();
    mountPanel();

    await user.click(screen.getByRole('button', { name: 'Configure Self Checks' }));
    const prompt = await screen.findByLabelText('Input Prompt template');
    await user.clear(prompt);
    await user.type(prompt, 'Check: ');
    await user.click(screen.getByRole('button', { name: /Insert \{\{ user_input \}\}/ }));

    await waitFor(() => {
      expect(prompt).toHaveValue('Check: {{ user_input }}');
    });
  });
});
