// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RailsConfig } from '@nemo/sdk/generated/platform/schema';
import { TooltipProvider } from '@nvidia/foundations-react-core';
import type { Meta, StoryObj } from '@storybook/react';
import { GuardrailConfigurationPanel } from '@studio/routes/guardrails/GuardrailConfigTab/GuardrailConfigurationPanel';
import {
  type GuardrailFormValues,
  mapConfigToForm,
} from '@studio/routes/guardrails/GuardrailForm/formModel';
import type { FC } from 'react';
import { FormProvider, useForm } from 'react-hook-form';

/**
 * Renders the panel against a real form, so the switches and the settings side panel
 * behave exactly as they do in the app — without needing a running platform.
 */
const WithForm: FC<{ config?: RailsConfig }> = ({ config }) => {
  const form = useForm<GuardrailFormValues>({ defaultValues: mapConfigToForm(config) });
  return (
    <TooltipProvider>
      <FormProvider {...form}>
        <div className="max-w-[1100px] p-density-2xl">
          <GuardrailConfigurationPanel />
        </div>
      </FormProvider>
    </TooltipProvider>
  );
};

const meta = {
  title: 'Guardrails/GuardrailConfigurationPanel',
  component: WithForm,
} satisfies Meta<typeof WithForm>;

export default meta;

type Story = StoryObj<typeof meta>;

/** A brand new guardrail: every rail off, nothing configured yet. */
export const Empty: Story = {
  args: {},
};

/** Self check running on both stages. */
export const SelfCheckEnabled: Story = {
  args: {
    config: {
      rails: {
        input: { flows: ['self check input'] },
        output: { flows: ['self check output'] },
      },
      prompts: [
        { task: 'self_check_input', content: 'Should the user message be blocked?' },
        { task: 'self_check_output', content: 'Should the bot message be blocked?' },
      ],
    },
  },
};

/**
 * Running on input only — the state the row could not previously express, and the reason
 * the stage badges carry state at all.
 */
export const SelfCheckInputOnly: Story = {
  args: {
    config: {
      rails: { input: { flows: ['self check input'] } },
      prompts: [{ task: 'self_check_input', content: 'Should the user message be blocked?' }],
    },
  },
};

/**
 * Switched off but still holding prompts, which is when the list offers to discard them.
 */
export const DisabledWithStoredSettings: Story = {
  args: {
    config: {
      prompts: [{ task: 'self_check_input', content: 'My tuned policy.' }],
    },
  },
};

/**
 * A config with its main model set — the model completions are generated against when the
 * guardrail's tests run. Sits alongside a task LLM to show the two are distinct: only the
 * `main` entry populates the field.
 */
export const WithMainModel: Story = {
  args: {
    config: {
      models: [
        { type: 'main', engine: 'nim', mode: 'chat', model: 'default/llama-3.1-8b-instruct' },
        { type: 'content_safety', engine: 'nim', model: 'system/nemoguard-8b-content-safety' },
      ],
    },
  },
};

/**
 * A config whose other rails Studio cannot configure yet. They stay in the saved document
 * untouched and remain visible in the read-only sections further down the tab.
 */
export const AlongsideUnsupportedRails: Story = {
  args: {
    config: {
      models: [
        { type: 'content_safety', engine: 'nim', model: 'system/nemoguard-8b-content-safety' },
      ],
      rails: {
        input: {
          flows: ['content safety check input $model=content_safety', 'self check input'],
        },
        config: { gliner: { server_endpoint: 'http://gliner.local' } },
      },
      prompts: [
        { task: 'self_check_input', content: 'Should the user message be blocked?' },
        {
          task: 'content_safety_check_input $model=content_safety',
          content: 'Check for unsafe content.',
          output_parser: 'nemoguard_parse_prompt_safety',
        },
      ],
    },
  },
};
