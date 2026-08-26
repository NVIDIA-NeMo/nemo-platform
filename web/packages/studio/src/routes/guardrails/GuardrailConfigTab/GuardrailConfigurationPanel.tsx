// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { WorkspaceModelSelect } from '@nemo/common/src/components/ModelSelectV2';
import type { RailsConfig } from '@nemo/sdk/generated/platform/schema';
import { Divider, FormField, Panel, Stack, Text } from '@nvidia/foundations-react-core';
import { useWorkspaceFromPathIfExists } from '@studio/hooks/useWorkspaceFromPath';
import {
  getMainModelName,
  setMainModelName,
} from '@studio/routes/guardrails/GuardrailConfigTab/mainModel';
import type { GuardrailFormValues } from '@studio/routes/guardrails/GuardrailForm/formModel';
import { RailsList } from '@studio/routes/guardrails/rails/RailsList';
import type { FC } from 'react';
import { useController, useFormContext } from 'react-hook-form';

/**
 * The guardrail's main editing surface: the main model, then the rails themselves.
 */
export const GuardrailConfigurationPanel: FC = () => {
  // Not the strict `useWorkspaceFromPath`: that throws when the param is absent, and the
  // panel renders fine without one — the model select simply fetches nothing.
  const workspace = useWorkspaceFromPathIfExists();
  const { control } = useFormContext<GuardrailFormValues>();
  const { field } = useController({ control, name: 'config' });
  const config = field.value as RailsConfig;

  const update = (next: Partial<RailsConfig>) => field.onChange({ ...config, ...next });
  const mainModel = getMainModelName(config.models);

  return (
    <Panel slotHeading="Guardrail Configuration" elevation="high" density="compact">
      <Stack gap="density-xl">
        <Text kind="body/regular/sm" className="text-text-secondary">
          Configure the NeMo Guardrails library to define LLM models, guardrails behavior, prompts,
          knowledge base settings, and tracing options.
        </Text>

        {/*
          Scoped deliberately to testing: at inference time IGW routes on the request's model,
          not this field (see resolveConfigModel). Promising more would be a lie the first time
          someone attaches this config to a VirtualModel.
        */}
        <FormField
          slotLabel="Main Model"
          slotHelp="The model completions are generated against when you run this guardrail's tests."
        >
          <WorkspaceModelSelect
            workspace={workspace || null}
            value={mainModel ? { model: mainModel } : null}
            onValueChange={(selection) =>
              update({ models: setMainModelName(config.models, selection.model) })
            }
            placeholder="Select a model"
            aria-label="Main Model"
            hideAdapters
            fullWidth
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
