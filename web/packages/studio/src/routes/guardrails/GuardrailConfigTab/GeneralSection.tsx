// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Divider, FormField, Panel, Stack, TextArea } from '@nvidia/foundations-react-core';
import type { GuardrailFormValues } from '@studio/routes/guardrails/GuardrailForm/formModel';
import { MessageSquareText } from 'lucide-react';
import { type FC, Fragment } from 'react';
import { useFormContext } from 'react-hook-form';

interface GeneralField {
  name: keyof GuardrailFormValues;
  label: string;
  description: string;
  placeholder: string;
}

const FIELDS: GeneralField[] = [
  {
    name: 'generalInstruction',
    label: 'General instruction',
    description:
      'Plain-language guidance the assistant follows. Injected into the guardrail prompts as the base instruction.',
    placeholder:
      'e.g. The assistant is a helpful support agent for NVIDIA products. It is polite and never discusses competitors.',
  },
  {
    name: 'sampleConversation',
    label: 'Sample conversation',
    description:
      'An example dialogue included in the guardrail prompts to demonstrate the desired tone and format.',
    placeholder: 'user: Hi!\nassistant: Hello! How can I help you today?',
  },
];

/**
 * The "General" panel: free-text fields that shape the guardrail prompts, bound
 * to the RHF form model. Their mapping to/from the config schema (e.g. the
 * instruction ↔ first `general` entry in `instructions[]`) lives in formModel.
 */
export const GeneralSection: FC = () => {
  const {
    register,
    formState: { errors },
  } = useFormContext<GuardrailFormValues>();

  return (
    <Panel
      slotHeading="General"
      slotIcon={<MessageSquareText />}
      elevation="high"
      density="compact"
    >
      <Stack gap="density-lg">
        {FIELDS.map((field, index) => (
          <Fragment key={field.name}>
            {index > 0 ? <Divider /> : null}
            <FormField
              slotLabel={field.label}
              slotHelp={field.description}
              status={errors[field.name] ? 'error' : undefined}
              slotError={errors[field.name]?.message}
            >
              {/*
                No `rows`: it fights `field-sizing: content` (from resizeable="auto"),
                which clips the top and offsets the scrollbar on long values. The base
                style's `min-height: 3lh` provides the floor; --max-auto-height the cap.
              */}
              <TextArea
                resizeable="auto"
                className="w-full"
                placeholder={field.placeholder}
                {...register(field.name)}
              />
            </FormField>
          </Fragment>
        ))}
      </Stack>
    </Panel>
  );
};
