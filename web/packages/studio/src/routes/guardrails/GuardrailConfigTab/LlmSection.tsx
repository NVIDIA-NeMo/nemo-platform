// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RailsConfigOutput } from '@nemo/sdk/generated/platform/schema';
import {
  AccordionContent,
  AccordionItem,
  AccordionRoot,
  AccordionTrigger,
  Divider,
  Panel,
  Stack,
  Text,
} from '@nvidia/foundations-react-core';
import {
  EmptyText,
  FieldList,
} from '@studio/routes/guardrails/GuardrailConfigTab/configPrimitives';
import { GENERAL_INSTRUCTION_TYPE } from '@studio/routes/guardrails/GuardrailConfigTab/instructions';
import type { Field } from '@studio/routes/guardrails/GuardrailConfigTab/types';
import { Bot } from 'lucide-react';
import { Fragment, type FC } from 'react';

/** The general instruction has its own editable field; exclude it here. */
const nonGeneralInstructions = (data: RailsConfigOutput | undefined) =>
  (data?.instructions ?? []).filter((instruction) => instruction.type !== GENERAL_INSTRUCTION_TYPE);

/** A read-only multi-line text block (instructions). */
const TextBlock: FC<{ label: string; content: string }> = ({ label, content }) => (
  <Stack gap="density-xs">
    <Text kind="label/bold/sm">{label}</Text>
    <Text
      kind="body/regular/sm"
      className="whitespace-pre-wrap rounded bg-surface-raised p-density-md"
    >
      {content}
    </Text>
  </Stack>
);

const hasLlmContent = (data: RailsConfigOutput | undefined): boolean =>
  Boolean(
    data?.models?.length ||
    nonGeneralInstructions(data).length ||
    data?.prompts?.length ||
    data?.prompting_mode ||
    data?.lowest_temperature != null ||
    data?.enable_multi_step_generation != null
  );

export const LlmSection: FC<{ data: RailsConfigOutput | undefined }> = ({ data }) => {
  if (!hasLlmContent(data)) return null;

  const models = data?.models ?? [];
  const instructions = nonGeneralInstructions(data);
  const prompts = data?.prompts ?? [];

  const settings: Field[] = [];
  if (data?.prompting_mode) settings.push({ label: 'Prompting mode', value: data.prompting_mode });
  if (data?.lowest_temperature != null) {
    settings.push({ label: 'Lowest temperature', value: String(data.lowest_temperature) });
  }
  if (data?.enable_multi_step_generation != null) {
    settings.push({
      label: 'Multi-step generation',
      value: data.enable_multi_step_generation ? 'Enabled' : 'Disabled',
    });
  }

  return (
    <Panel
      slotHeading="Models &amp; prompting"
      slotIcon={<Bot />}
      elevation="high"
      density="compact"
    >
      <Stack gap="density-md">
        {models.length ? (
          <Stack gap="density-sm">
            <Text kind="label/bold/sm">Models ({models.length})</Text>
            {models.map((model, index) => (
              <Fragment key={`${model.type}-${model.model ?? index}`}>
                {index > 0 ? <Divider /> : null}
                <FieldList
                  fields={[
                    { label: 'Type', value: model.type },
                    { label: 'Engine', value: model.engine },
                    ...(model.model ? [{ label: 'Model', value: model.model }] : []),
                    ...(model.mode ? [{ label: 'Mode', value: model.mode }] : []),
                  ]}
                />
              </Fragment>
            ))}
          </Stack>
        ) : null}

        {instructions.map((instruction, index) => (
          <TextBlock
            key={`${instruction.type}-${index}`}
            label={`Instructions (${instruction.type})`}
            content={instruction.content}
          />
        ))}

        <FieldList fields={settings} />

        {prompts.length ? (
          <Stack gap="density-sm">
            <Text kind="label/bold/sm">Prompt overrides ({prompts.length})</Text>
            <AccordionRoot multiple>
              {prompts.map((prompt, index) => (
                <AccordionItem key={`${prompt.task}-${index}`} value={`${prompt.task}-${index}`}>
                  <AccordionTrigger>
                    <Text kind="body/regular/sm">{prompt.task}</Text>
                  </AccordionTrigger>
                  <AccordionContent>
                    {prompt.content ? (
                      <Text
                        kind="body/regular/sm"
                        className="whitespace-pre-wrap rounded bg-surface-raised p-density-md"
                      >
                        {prompt.content}
                      </Text>
                    ) : (
                      <EmptyText>
                        This prompt uses a message-template format (see raw config).
                      </EmptyText>
                    )}
                  </AccordionContent>
                </AccordionItem>
              ))}
            </AccordionRoot>
          </Stack>
        ) : null}
      </Stack>
    </Panel>
  );
};
