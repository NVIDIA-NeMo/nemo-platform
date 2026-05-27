// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { RadioCard } from '@nemo/common/src/components/RadioCard';
import { Block, Flex, RadioGroupRoot, Stack, Switch, Text } from '@nvidia/foundations-react-core';
import { LoraParameters } from '@studio/components/customizer/CustomizationHyperparameters/LoraParameters';
import { type CustomizationFormFields } from '@studio/components/NewCustomizationForm';
import { DEFAULT_LORA_VALUES } from '@studio/components/NewCustomizationForm/constants';
import { FormSection } from '@studio/components/NewCustomizationForm/FormSection';
import { useFormContext, useWatch } from 'react-hook-form';

export const ParameterEfficiency = () => {
  const {
    control,
    formState: { disabled },
    setValue,
  } = useFormContext<CustomizationFormFields>();

  const peft = useWatch({ control, name: 'training.peft' });
  const isLora = !!peft;

  const handlePeftChange = (value: string) => {
    if (value === 'lora') {
      setValue('training.peft', DEFAULT_LORA_VALUES, { shouldValidate: true });
    } else {
      setValue('training.peft', undefined, { shouldValidate: true });
    }
  };

  const handleMergeChange = (checked: boolean) => {
    setValue('training.peft.merge', checked, { shouldValidate: true });
  };

  return (
    <FormSection
      title="Parameter Efficiency"
      description="Use LoRA (Low-rank Adaptation) as it is more memory-efficient and performs similarly to full fine-tuning."
    >
      <Block data-testid="parameter-efficiency-select">
        <RadioGroupRoot
          name="parameter-efficiency"
          orientation="vertical"
          className="w-full"
          value={isLora ? 'lora' : 'full_weights'}
          onValueChange={handlePeftChange}
          disabled={disabled}
        >
          <Flex gap="density-xl">
            <RadioCard
              value="lora"
              label="LoRA"
              description={
                <Stack gap="density-sm">
                  <Text kind="body/regular/md" color="secondary">
                    Low-rank Adaptation. Freeze base weights, train small adapters.
                  </Text>
                  {isLora && (
                    <Flex align="center" gap="density-sm" onClick={(e) => e.stopPropagation()}>
                      <Switch
                        checked={peft?.merge ?? false}
                        onCheckedChange={handleMergeChange}
                        size="small"
                        slotLabel="Merge Weights"
                      />
                    </Flex>
                  )}
                </Stack>
              }
              labelSide="left"
            />
            <RadioCard
              value="full_weights"
              label="Full Weights Fine-tuning"
              description="Update all model weights for best performance; needs more compute and training."
              labelSide="left"
            />
          </Flex>
        </RadioGroupRoot>
      </Block>

      {isLora && <LoraParameters />}
    </FormSection>
  );
};
