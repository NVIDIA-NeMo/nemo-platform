// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ControlledTextInput } from '@nemo/common/src/components/form/ControlledTextInput';
import { Stack, Text } from '@nvidia/foundations-react-core';
import { ControlledStringListInput } from '@studio/components/NewCustomizationForm/ControlledStringListInput';
import { FormSection } from '@studio/components/NewCustomizationForm/FormSection';
import type { CustomizationFormFields } from '@studio/util/forms/customization';
import { useFormContext } from 'react-hook-form';

/**
 * Experiment-tracking configuration for RL jobs. Everything here is optional — a blank
 * field is stripped on submit so the job ships without the integration rather than with
 * an empty one.
 */
export const RlIntegrationsSection = () => {
  const { control, formState } = useFormContext<CustomizationFormFields>();
  const disabled = formState.isSubmitting;

  return (
    <FormSection
      collapsible
      title="Experiment Tracking"
      description="Optional. Stream metrics to Weights & Biases or MLflow while the job runs."
    >
      <Stack gap="density-md">
        <Text kind="label/bold/sm">Weights &amp; Biases</Text>
        <ControlledTextInput
          useControllerProps={{ name: 'rl.integrations.wandb.project', control }}
          formFieldProps={{ slotLabel: 'Project' }}
          disabled={disabled}
        />
        <ControlledTextInput
          useControllerProps={{ name: 'rl.integrations.wandb.name', control }}
          formFieldProps={{ slotLabel: 'Run Name' }}
          disabled={disabled}
        />
        <ControlledTextInput
          useControllerProps={{ name: 'rl.integrations.wandb.entity', control }}
          formFieldProps={{ slotLabel: 'Entity' }}
          disabled={disabled}
        />
        <ControlledStringListInput
          useControllerProps={{ name: 'rl.integrations.wandb.tags', control }}
          formFieldProps={{
            slotLabel: 'Tags',
            slotInfo: 'Comma separated labels attached to the W&B run.',
          }}
          placeholder="grpo, recipe-aligned"
          disabled={disabled}
        />
        <ControlledTextInput
          useControllerProps={{ name: 'rl.integrations.wandb.notes', control }}
          formFieldProps={{ slotLabel: 'Notes' }}
          disabled={disabled}
        />
        <ControlledTextInput
          useControllerProps={{ name: 'rl.integrations.wandb.base_url', control }}
          formFieldProps={{
            slotLabel: 'Base URL',
            slotInfo: 'Only needed for a self-hosted W&B instance.',
          }}
          disabled={disabled}
        />
        <ControlledTextInput
          useControllerProps={{ name: 'rl.integrations.wandb.api_key_secret', control }}
          formFieldProps={{
            slotLabel: 'API Key Secret',
            slotInfo:
              "Name of a stored secret holding the W&B API key, as 'secret-name' or 'workspace/secret-name'. The key itself is never entered here.",
          }}
          placeholder="wandb-api-key"
          disabled={disabled}
        />

        <Text kind="label/bold/sm">MLflow</Text>
        <ControlledTextInput
          useControllerProps={{ name: 'rl.integrations.mlflow.experiment_name', control }}
          formFieldProps={{ slotLabel: 'Experiment Name' }}
          disabled={disabled}
        />
        <ControlledTextInput
          useControllerProps={{ name: 'rl.integrations.mlflow.name', control }}
          formFieldProps={{ slotLabel: 'Run Name' }}
          disabled={disabled}
        />
        <ControlledTextInput
          useControllerProps={{ name: 'rl.integrations.mlflow.description', control }}
          formFieldProps={{ slotLabel: 'Description' }}
          disabled={disabled}
        />
        <ControlledTextInput
          useControllerProps={{ name: 'rl.integrations.mlflow.tracking_uri', control }}
          formFieldProps={{ slotLabel: 'Tracking URI' }}
          disabled={disabled}
        />
      </Stack>
    </FormSection>
  );
};
