// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { UseControllerComponentProps } from '@nemo/common/src/types';
import { FormField, Slider } from '@nvidia/foundations-react-core';
import type { ComponentProps } from 'react';
import { useController } from 'react-hook-form';

type SliderProps = ComponentProps<typeof Slider>;

interface Props extends SliderProps, UseControllerComponentProps {
  /**
   * Validate the value of the slider before changing it
   * @returns true if the value is valid, false otherwise
   */
  validate?: (value: number) => boolean;
  onValueChange?: (value: number) => void;
}

export const ControlledSlider = ({
  onValueChange,
  validate,
  useControllerProps,
  formFieldProps,
  ...sliderProps
}: Props) => {
  const {
    field: { onBlur, onChange: onChangeControl, value, disabled: disabledControl },
    fieldState: { error },
  } = useController(useControllerProps);

  const handleValueChange = (newValue: number) => {
    if (validate && !validate(newValue)) {
      return;
    }
    onValueChange?.(newValue);
    onChangeControl(newValue);
  };

  return (
    <FormField
      name={useControllerProps.name}
      slotError={error?.message?.toString()}
      status={error ? 'error' : undefined}
      {...formFieldProps}
    >
      <Slider
        orientation="horizontal"
        className="mb-5"
        value={
          typeof value === 'number' ? value : (sliderProps.defaultValue ?? sliderProps.min ?? 0)
        }
        disabled={sliderProps.disabled ?? disabledControl}
        min={sliderProps.min ?? 0}
        max={sliderProps.max ?? 100}
        step={sliderProps.step ?? 1}
        stepPosition="end"
        aria-label={sliderProps['aria-label'] || 'Controlled slider'}
        onValueChange={handleValueChange}
        onBlur={onBlur}
        {...sliderProps}
      />
    </FormField>
  );
};
