// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { UseControllerComponentProps } from '@nemo/common/src/types';
import { Flex, FormField, Switch } from '@nvidia/foundations-react-core';
import { ComponentProps, FC } from 'react';
import { useController } from 'react-hook-form';

interface Props
  extends
    Omit<ComponentProps<typeof Switch>, 'attributes' | 'onChange'>,
    UseControllerComponentProps {
  onChange?: (value: boolean) => void;
  attributes?: {
    Flex?: ComponentProps<typeof Flex>;
  };
}

export const ControlledSwitch: FC<Props> = ({
  useControllerProps,
  formFieldProps,
  onChange,
  attributes,
  ...props
}) => {
  const { field } = useController(useControllerProps);

  const wrappedOnChange = (checked: boolean) => {
    onChange?.(checked);
    field.onChange(checked);
  };

  return (
    <FormField {...formFieldProps}>
      {() => (
        <Flex className="w-full" justify="end" {...attributes?.Flex}>
          <Switch
            className="relative"
            name={field.name}
            ref={field.ref}
            onBlur={field.onBlur}
            checked={field.value}
            onCheckedChange={wrappedOnChange}
            {...props}
          />
        </Flex>
      )}
    </FormField>
  );
};
