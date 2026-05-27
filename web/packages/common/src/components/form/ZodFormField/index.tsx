// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ControlledCombobox } from '@nemo/common/src/components/form/ControlledCombobox';
import { ControlledSelect } from '@nemo/common/src/components/form/ControlledSelect';
import { ControlledSliderWithTextInput } from '@nemo/common/src/components/form/ControlledSliderWithTextInput';
import { ControlledSwitch } from '@nemo/common/src/components/form/ControlledSwitch';
import { ControlledTextArea } from '@nemo/common/src/components/form/ControlledTextArea';
import { ControlledTextInput } from '@nemo/common/src/components/form/ControlledTextInput';
import {
  getBaseSchema,
  getDefaultValue,
  getEnumValues,
  getFieldName,
  getUnionOptions,
  isRequired,
} from '@nemo/common/src/components/form/ZodFormField/utils';
import { UseControllerComponentProps } from '@nemo/common/src/types';
import { isDefined } from '@nemo/common/src/utils/isDefined';
import { FormField, FormFieldProps, Text } from '@nvidia/foundations-react-core';
import { useFormContext } from 'react-hook-form';
import { z } from 'zod';

interface ZodFormFieldProps extends UseControllerComponentProps {
  schema: z.ZodTypeAny;
  defaultValue?: string | string[] | number | boolean;
  min?: number;
  max?: number;
  step?: number;
  placeholder?: string;
  items?: string[];
  disabled?: boolean;
  required?: boolean;
  onChange?: (value: string | number | boolean | string[] | undefined, name: string) => void;
}

/*
 * This component is used to generate a form field based on a Zod schema.
 * It will automatically generate the appropriate form field component based on the Zod schema.
 */
export const ZodFormField = ({
  schema,
  defaultValue,
  min,
  max,
  step,
  placeholder,
  items = [],
  disabled = false,
  required = false,
  onChange,
  useControllerProps,
  formFieldProps,
}: ZodFormFieldProps) => {
  const name = useControllerProps.name;
  const { formState, getFieldState } = useFormContext();
  const { error } = getFieldState(name);
  const baseSchema = getBaseSchema(schema);
  const fieldDefaultValue = getDefaultValue(schema, defaultValue);
  const fieldDisabled = disabled || formState.disabled;
  const fieldRequired = isRequired(schema, required);

  const fieldLabel = formFieldProps?.slotLabel ?? getFieldName(name);
  const fieldInfo = formFieldProps?.slotInfo ?? schema.description;
  const isLeftLabel = formFieldProps?.labelPosition === 'left';

  // Assign form field props unless already provided
  const composedFormFieldProps: FormFieldProps = {
    ...formFieldProps,
    required: fieldRequired,
    slotLabel: isLeftLabel ? <Text kind="label/regular/md">{fieldLabel}</Text> : fieldLabel,
    slotInfo: fieldInfo,
  };

  // Handle ZodArray (including optional arrays)
  if (baseSchema instanceof z.ZodArray) {
    const elementSchema = baseSchema.element;

    // If it's an array of strings, use a multi-select combobox
    if (elementSchema instanceof z.ZodString) {
      return (
        <ControlledCombobox
          kind="multiple"
          items={items}
          placeholder={placeholder || 'Select options...'}
          disabled={fieldDisabled}
          required={fieldRequired}
          onChange={(value) => onChange?.(value, name)}
          formFieldProps={composedFormFieldProps}
          useControllerProps={useControllerProps}
        />
      );
    }

    // For other array types, you might want to create a different component
    // For now, fall back to a text input that accepts comma-separated values
    return (
      <ControlledTextInput
        placeholder={placeholder || 'Enter comma-separated values...'}
        required={fieldRequired}
        disabled={fieldDisabled}
        onChange={(e) => onChange?.(e.currentTarget.value, name)}
        formFieldProps={composedFormFieldProps}
        useControllerProps={useControllerProps}
      />
    );
  }

  // Handle ZodString
  if (baseSchema instanceof z.ZodString) {
    // Check if it's a long string (use textarea)
    if (baseSchema.maxLength && baseSchema.maxLength > 100) {
      return (
        <ControlledTextArea
          disabled={fieldDisabled}
          defaultValue={fieldDefaultValue ? String(fieldDefaultValue) : undefined}
          onChange={(value) => {
            onChange?.(value || '', name);
          }}
          formFieldProps={composedFormFieldProps}
          useControllerProps={useControllerProps}
        />
      );
    }

    // Check if it's an enum or has specific options
    const enumValues = getEnumValues(baseSchema);
    if (enumValues.length > 0) {
      return (
        <ControlledSelect
          items={enumValues.map((value) => ({ children: value, value }))}
          placeholder={placeholder || 'Select an option...'}
          disabled={fieldDisabled}
          onChange={(value) => onChange?.(value, name)}
          formFieldProps={composedFormFieldProps}
          useControllerProps={useControllerProps}
        />
      );
    }

    // Default to text input
    return (
      <ControlledTextInput
        placeholder={placeholder}
        required={fieldRequired}
        disabled={fieldDisabled}
        defaultValue={fieldDefaultValue ? String(fieldDefaultValue) : undefined}
        onChange={(e) => onChange?.(e.currentTarget.value, name)}
        formFieldProps={composedFormFieldProps}
        useControllerProps={useControllerProps}
      />
    );
  }

  // Handle ZodNumber
  if (baseSchema instanceof z.ZodNumber) {
    if (isDefined(min) && isDefined(max)) {
      return (
        <ControlledSliderWithTextInput
          disabled={fieldDisabled}
          min={min}
          max={max}
          step={step}
          defaultValue={Number(fieldDefaultValue ?? min)}
          useControllerProps={useControllerProps}
          formFieldProps={composedFormFieldProps}
        />
      );
    }
    return (
      <ControlledTextInput
        type="number"
        defaultValue={fieldDefaultValue?.toString()}
        placeholder={placeholder}
        required={fieldRequired}
        disabled={fieldDisabled}
        onChange={(e) => onChange?.(e.currentTarget.value, name)}
        formFieldProps={composedFormFieldProps}
        useControllerProps={useControllerProps}
      />
    );
  }

  // Handle ZodBoolean
  if (baseSchema instanceof z.ZodBoolean) {
    return (
      <ControlledSwitch
        disabled={fieldDisabled}
        onChange={(value) => onChange?.(value, name)}
        useControllerProps={useControllerProps}
        formFieldProps={composedFormFieldProps}
      />
    );
  }

  // Handle ZodUnion
  if (baseSchema instanceof z.ZodUnion) {
    const unionOptions = getUnionOptions(baseSchema);

    if (unionOptions.length > 0) {
      return (
        <ControlledSelect
          items={unionOptions.map((option) => ({ children: option, value: option }))}
          placeholder={placeholder || 'Select an option...'}
          disabled={fieldDisabled}
          onChange={(value) => onChange?.(value, name)}
          formFieldProps={composedFormFieldProps}
          useControllerProps={useControllerProps}
        />
      );
    }
  }

  // Handle ZodEnum
  if (baseSchema instanceof z.ZodEnum) {
    const enumValues = getEnumValues(baseSchema);

    if (enumValues.length > 0) {
      return (
        <ControlledSelect
          items={enumValues.map((value) => ({ children: value, value }))}
          placeholder={placeholder || 'Select an option...'}
          disabled={fieldDisabled}
          onChange={(value) => onChange?.(value, name)}
          formFieldProps={composedFormFieldProps}
          useControllerProps={useControllerProps}
        />
      );
    }
  }

  // Handle ZodLiteral
  if (baseSchema instanceof z.ZodLiteral) {
    const literalValue = baseSchema.value;
    return (
      <ControlledTextInput
        value={literalValue}
        disabled // Literals are read-only
        formFieldProps={{
          slotInfo: `Fixed value: ${literalValue}`,
          ...formFieldProps,
        }}
        useControllerProps={useControllerProps}
      />
    );
  }

  // Handle ZodObject (nested objects)
  if (baseSchema instanceof z.ZodObject) {
    const fields = Object.entries(baseSchema.shape).map(([key, value]) => (
      <ZodFormField
        key={key}
        schema={value as z.ZodTypeAny}
        useControllerProps={{ ...useControllerProps, name: `${name}.${key}` }}
        disabled={fieldDisabled}
      />
    ));
    return (
      <FormField
        name={name}
        slotError={error?.message}
        status={error && 'error'}
        required={fieldRequired}
        {...formFieldProps}
      >
        <div className="p-4 border border-dashed border-gray-300 rounded text-center text-gray-500">
          Nested object field: {name}
          {fields}
        </div>
      </FormField>
    );
  }

  // Fallback for unknown types
  return (
    <FormField
      name={name}
      slotError={error?.message}
      status={error && 'error'}
      required={fieldRequired}
      {...formFieldProps}
    >
      <div className="p-4 border border-dashed border-gray-300 rounded text-center text-gray-500">
        Unsupported field type: {baseSchema.constructor.name}
      </div>
    </FormField>
  );
};
