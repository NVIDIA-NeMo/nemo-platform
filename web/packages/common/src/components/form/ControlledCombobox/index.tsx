// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { TextInputSpinner } from '@nemo/common/src/components/form/TextInputSpinner';
import { UseControllerComponentProps } from '@nemo/common/src/types';
import { Combobox, ComboboxProps, FormField } from '@nvidia/foundations-react-core';
import { ReactNode, useState } from 'react';
import { useController } from 'react-hook-form';

// Generic type to handle both single and multiple selection
type ComboboxValue<T extends 'single' | 'multiple'> = T extends 'single' ? string : string[];

interface Props<T extends 'single' | 'multiple' = 'single'>
  // Omit ensures type safety and avoids uncontrolled component state
  extends
    Omit<
      ComboboxProps,
      | 'onChange'
      | 'defaultValue'
      | 'multiple'
      | 'kind'
      | 'value'
      | 'onValueChange'
      | 'inputValue'
      | 'onInputValueChange'
      | 'renderValue'
      | 'ref'
    >,
    UseControllerComponentProps {
  label?: string;
  loading?: boolean;
  onChange?: (value: ComboboxValue<T>) => void;
  width?: string;
  hideError?: boolean;
  kind?: T;
  renderValue?: (
    value: string | string[] | undefined,
    setValue:
      | ((nextValue: string | string[]) => void)
      | ((nextValueFunc: (prevValue: string | string[]) => string | string[]) => void)
  ) => ReactNode;
  /**
   * Allow users to input a value that is not in the list. Also causes the value to not reset on blur.
   * @default false
   */
  freeForm?: boolean;
}

export const ControlledCombobox = <T extends 'single' | 'multiple' = 'single'>({
  items = [],
  label,
  loading,
  onChange,
  width,
  hideError = false,
  useControllerProps,
  formFieldProps,
  kind = 'single' as T,
  renderValue,
  freeForm = false,
  ...comboboxProps
}: Props<T>) => {
  const {
    field: { onBlur, onChange: onChangeControl, value },
    fieldState: { error },
  } = useController(useControllerProps);
  const [dispValue, setDispValue] = useState(value);

  const handleSelectedValueChange = (newValue: string | string[]) => {
    setDispValue(newValue);
    onChange?.(newValue as ComboboxValue<T>);
    onChangeControl(newValue);
  };

  const handleTempValueChange = (newValue: string) => {
    // In freeForm, we set form value to enable custom values.
    if (freeForm) {
      handleSelectedValueChange(newValue);
    } else {
      setDispValue(newValue);
    }
  };
  return (
    <FormField
      name={useControllerProps.name}
      slotLabel={label}
      slotError={hideError ? undefined : error?.message}
      status={error && 'error'}
      {...formFieldProps}
    >
      {({ status, ...args }) => {
        const baseProps = {
          status,
          style: { width },
          id: useControllerProps.name,
          name: useControllerProps.name,
          items,
          inputValue: kind === 'multiple' ? '' : dispValue || '',
          onInputValueChange: handleTempValueChange,
          onBlur,
          slotEnd: loading && <TextInputSpinner />,
          resetValueOnBlur: !freeForm,
          renderValue,
          ...comboboxProps,
          attributes: {
            ComboboxTrigger: {
              ...args,
              spellCheck: false,
              ...comboboxProps?.attributes?.ComboboxTrigger,
            },
          },
        };

        if (kind === 'multiple') {
          return (
            <Combobox
              {...baseProps}
              multiple
              value={value as string[]}
              onValueChange={(newValue: string[]) => handleSelectedValueChange(newValue)}
            />
          );
        } else {
          return (
            <Combobox
              {...baseProps}
              value={value as string}
              onValueChange={(newValue: string) => handleSelectedValueChange(newValue)}
            />
          );
        }
      }}
    </FormField>
  );
};
