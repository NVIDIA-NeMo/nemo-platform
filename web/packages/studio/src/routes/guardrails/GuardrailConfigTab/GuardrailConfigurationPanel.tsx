// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RailsConfig } from '@nemo/sdk/generated/platform/schema';
import { Divider, FormField, Panel, Stack, Text, TextArea } from '@nvidia/foundations-react-core';
import {
  getGeneralInstruction,
  setGeneralInstruction,
} from '@studio/routes/guardrails/GuardrailConfigTab/instructions';
import type { GuardrailFormValues } from '@studio/routes/guardrails/GuardrailForm/formModel';
import { RailsList } from '@studio/routes/guardrails/rails/RailsList';
import type { FC } from 'react';
import { useController, useFormContext } from 'react-hook-form';

/**
 * The guardrail's main editing surface: the instructions that frame every rail prompt,
 * then the rails themselves.
 *
 * Both text fields write through the same `config` controller the rails use, so the
 * document is the only copy of them. Binding a controller to `config.instructions`
 * directly would register a path most configs don't have, which react-hook-form counts as
 * a change and reports as unsaved edits on an untouched form.
 */
export const GuardrailConfigurationPanel: FC = () => {
  const { control } = useFormContext<GuardrailFormValues>();
  const { field } = useController({ control, name: 'config' });
  const config = field.value as RailsConfig;

  const update = (next: Partial<RailsConfig>) => field.onChange({ ...config, ...next });

  return (
    <Panel slotHeading="Guardrail Configuration" elevation="high" density="compact">
      <Stack gap="density-xl">
        <Text kind="body/regular/sm" className="text-text-secondary">
          Configure the NeMo Guardrails library to define LLM models, guardrails behavior, prompts,
          knowledge base settings, and tracing options.
        </Text>

        <FormField
          slotLabel="General Instructions"
          slotHelp="Instructions for the LLM (similar to system prompts)"
        >
          {/*
            No `rows`: it fights `field-sizing: content` (from resizeable="auto"), which
            clips the top and offsets the scrollbar on long values. The base style's
            `min-height: 3lh` provides the floor; --max-auto-height the cap.
          */}
          <TextArea
            resizeable="auto"
            className="w-full"
            aria-label="General Instructions"
            value={getGeneralInstruction(config.instructions)}
            onChange={(event) =>
              update({
                instructions: setGeneralInstruction(config.instructions, event.currentTarget.value),
              })
            }
          />
        </FormField>

        <FormField
          slotLabel="Sample Conversation"
          slotHelp="An example dialogue included in the guardrail prompts to demonstrate the desired tone and format."
        >
          <TextArea
            resizeable="auto"
            className="w-full"
            aria-label="Sample Conversation"
            value={config.sample_conversation ?? ''}
            onChange={(event) =>
              update({ sample_conversation: event.currentTarget.value || undefined })
            }
          />
        </FormField>

        <Divider />

        <Stack gap="density-md">
          <Text kind="label/bold/lg">Guardrails</Text>
          <RailsList data={config} onChange={field.onChange} />
        </Stack>
      </Stack>
    </Panel>
  );
};
