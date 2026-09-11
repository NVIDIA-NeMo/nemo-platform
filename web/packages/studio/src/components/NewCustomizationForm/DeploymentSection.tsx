// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Stack, Text } from '@nvidia/foundations-react-core';
import { ControlledJsonInput } from '@studio/components/NewCustomizationForm/ControlledJsonInput';
import { FormSection } from '@studio/components/NewCustomizationForm/FormSection';
import { producesAdapter, type CustomizationFormFields } from '@studio/util/forms/customization';
import type { FC } from 'react';
import { useFormContext, useWatch } from 'react-hook-form';

/**
 * How the fine-tuned model gets served once the job finishes.
 *
 * Only rendered for the unsloth backend. `deployment_config` exists solely on
 * `UnslothJobInput`; `AutomodelJobInput` and `RlJobInput` carry no deployment
 * field at all, so there is nothing to submit for them and an always-visible
 * section would promise something the API cannot honour. Those backends deploy
 * from the Deployments page after the job completes.
 */
export const DeploymentSection: FC = () => {
  const { control, formState } = useFormContext<CustomizationFormFields>();
  const backend = useWatch({ control, name: 'backend' });
  const unslothFinetuningType = useWatch({
    control,
    name: 'unsloth.training.finetuning_type',
  });

  if (backend !== 'unsloth') return null;

  const isAdapterRun = producesAdapter({
    backend,
    unsloth: { training: { finetuning_type: unslothFinetuningType } },
  });

  return (
    <FormSection
      title="Deployment"
      description="Optional. Leave blank to skip deployment and serve the model later from the Deployments page."
    >
      <Stack gap="density-lg">
        <ControlledJsonInput
          useControllerProps={{ name: 'unsloth.deployment_config', control }}
          formFieldProps={{
            slotLabel: 'Deploy After Training',
            slotInfo:
              'Name an existing deployment config to reuse it, or give inline NIM parameters as JSON (for example { "gpu": 1 }).',
          }}
          placeholder='"my-config"  or  { "gpu": 1 }'
          disabled={formState.isSubmitting}
        />
        {isAdapterRun ? (
          <Text kind="body/regular/sm" className="text-subtle">
            This run produces a LoRA adapter, which is served by a deployment of its base model with
            LoRA enabled — it is not deployed on its own.
          </Text>
        ) : (
          <Text kind="body/regular/sm" className="text-subtle">
            Set <code>lora_enabled</code> in the deployment parameters if you plan to serve LoRA
            adapters against these weights later.
          </Text>
        )}
      </Stack>
    </FormSection>
  );
};
