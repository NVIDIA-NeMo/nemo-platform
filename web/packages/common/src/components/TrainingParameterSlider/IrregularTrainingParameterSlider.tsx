// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  CustomizerHyperparameters,
  HYPERPARAMETER_FIELD_METADATA,
  validateTrainingParameterIsAllowed,
} from '@nemo/common/src/components/TrainingParameterSlider/types';
import { FormField, Slider } from '@nvidia/foundations-react-core';
import { FC, useState } from 'react';
import { Controller, FieldPath, FieldValues, useFormContext } from 'react-hook-form';

export interface TrainingParameterSliderProps {
  name: FieldPath<CustomizerHyperparameters>;
  disabled?: boolean;
  errorText?: string;
}

/** Irregular Training Parameter Slider
 * This component is used to create a slider with irregular step values.
 * since the step values are specific we don't need to include a text input for granular control.
 */
export const IrregularTrainingParameterSlider: FC<TrainingParameterSliderProps> = ({
  name,
  disabled,
  errorText: errorTextOverride,
}) => {
  const { control } = useFormContext<CustomizerHyperparameters>();

  const fieldMetadata = HYPERPARAMETER_FIELD_METADATA[name];
  const [sliderValue, setSliderValue] = useState(
    fieldMetadata.values?.indexOf(fieldMetadata.default) ?? 0
  );

  const handleSliderChange = (field: FieldValues, newValue: number) => {
    setSliderValue(newValue);
    field.onChange(fieldMetadata.values?.[newValue] ?? 0);
  };

  return (
    <Controller
      control={control}
      name={name}
      rules={{
        validate: {
          isAllowed: (value) =>
            validateTrainingParameterIsAllowed(value, [...(fieldMetadata.values ?? [])]),
        },
      }}
      render={({ field, fieldState }) => (
        <FormField
          slotLabel={fieldMetadata.name}
          slotHelp={fieldMetadata.description}
          slotError={fieldState.error?.message || errorTextOverride}
          status={fieldState.error?.message ? 'error' : undefined}
          required
          attributes={{
            FormFieldHelper: {
              className: 'pt-4',
            },
          }}
        >
          <Slider
            orientation="horizontal"
            value={sliderValue}
            onValueChange={(newValue) => handleSliderChange(field, newValue)}
            max={(fieldMetadata.values?.length ?? 0) - 1}
            min={0}
            step={1}
            disabled={disabled}
            stepPosition="end"
            stepFormatFn={(value) => fieldMetadata.values?.[value]?.toString() ?? '0'}
            aria-label="Controlled slider"
          />
        </FormField>
      )}
    />
  );
};
