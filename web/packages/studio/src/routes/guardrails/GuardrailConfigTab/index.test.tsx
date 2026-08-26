// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { GuardrailConfig, RailsConfig } from '@nemo/sdk/generated/platform/schema';
import { GuardrailConfigTab } from '@studio/routes/guardrails/GuardrailConfigTab';
import { GuardrailFormContext } from '@studio/routes/guardrails/GuardrailForm/context';
import {
  type GuardrailFormValues,
  mapConfigToForm,
} from '@studio/routes/guardrails/GuardrailForm/formModel';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { FC } from 'react';
import { FormProvider, useForm } from 'react-hook-form';

const mountTab = (data?: RailsConfig) => {
  const config = {
    name: 'demo',
    workspace: 'default',
    description: 'A demo config',
    data,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-02T00:00:00Z',
  } as GuardrailConfig;

  const Harness: FC = () => {
    const form = useForm<GuardrailFormValues>({ defaultValues: mapConfigToForm(data) });
    return (
      <TestProviders>
        <GuardrailFormContext.Provider
          value={{ config, save: () => {}, isSaving: false, resetToServer: () => {} }}
        >
          <FormProvider {...form}>
            <GuardrailConfigTab />
          </FormProvider>
        </GuardrailFormContext.Provider>
      </TestProviders>
    );
  };

  render(<Harness />);
};

/**
 * The JSON panel renders through CodeMirror, which splits each line into syntax-coloured
 * spans — so `getByText` on a key/value pair finds nothing. Read the editor's text instead.
 */
const configJson = () => screen.getByTestId('nv-code-editor-root').textContent ?? '';

describe('GuardrailConfigTab', () => {
  it('shows the rail editor and the resulting document, and nothing else', () => {
    mountTab();

    expect(screen.getByText('Guardrail Configuration')).toBeInTheDocument();
    expect(screen.getByText('Configuration JSON')).toBeInTheDocument();

    for (const removed of ['Overview', 'Pipeline', 'Detectors', 'Models & prompting']) {
      expect(screen.queryByText(removed)).not.toBeInTheDocument();
    }
  });

  it('shows the whole document, including parts no rail definition owns', () => {
    mountTab({
      models: [{ type: 'content_safety', engine: 'nim', model: 'system/nemoguard' }],
      rails: { config: { gliner: { server_endpoint: 'http://gliner.local' } } },
      custom_data: { team: 'platform' },
    });

    // These have no rail definition yet, so the JSON is the only place they are visible —
    // and the only proof the editor is not quietly dropping them.
    expect(configJson()).toContain('system/nemoguard');
    expect(configJson()).toContain('http://gliner.local');
    expect(configJson()).toContain('"team": "platform"');
  });

  it('tracks unsaved edits rather than the saved config', async () => {
    const user = userEvent.setup();
    mountTab();

    expect(configJson()).not.toContain('self check input');

    await user.click(screen.getByRole('switch', { name: 'Self Checks' }));

    // One switch writes the flow and the prompt its action renders — the JSON is where
    // that coupling becomes visible.
    await waitFor(() => {
      expect(configJson()).toContain('self check input');
    });
    expect(configJson()).toContain('self_check_input');
  });
});
