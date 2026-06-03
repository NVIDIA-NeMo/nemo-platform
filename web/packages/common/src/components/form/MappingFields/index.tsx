/*
 * SPDX-FileCopyrightText: Copyright (c) 2022-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 *
 * NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
 * property and proprietary rights in and to this material, related
 * documentation and any modifications thereto. Any use, reproduction,
 * disclosure or distribution of this material and related documentation
 * without an express license agreement from NVIDIA CORPORATION or
 * its affiliates is strictly prohibited.
 */

import { ControlledCombobox } from '@nemo/common/src/components/form/ControlledCombobox';
import { ControlledTextInput } from '@nemo/common/src/components/form/ControlledTextInput';
import { isDefined } from '@nemo/common/src/utils/isDefined';
import { Banner, Button, Flex, Stack } from '@nvidia/foundations-react-core';
import cn from 'classnames';
import { Trash } from 'lucide-react';
import { type ComponentProps, useEffect, useMemo } from 'react';
import {
  Control,
  FieldArrayPath,
  FieldValues,
  useFieldArray,
  useFormState,
  useWatch,
} from 'react-hook-form';

const DEFAULT_SCHEMA_VALUE = (key: string) => `{{{${key}}}}`;

function isMappingRowEmpty(row: { key?: string; value?: string } | undefined): boolean {
  const k = typeof row?.key === 'string' ? row.key.trim() : '';
  const v = row?.value == null ? '' : String(row.value).trim();
  return !k && !v;
}

function getAtPath(obj: unknown, path: string): unknown {
  if (!obj || typeof obj !== 'object') return undefined;
  const parts = path.split('.');
  let cur: unknown = obj;
  for (const p of parts) {
    if (cur === null || cur === undefined || typeof cur !== 'object') return undefined;
    cur = (cur as Record<string, unknown>)[p];
  }
  return cur;
}

function fieldArrayHasErrors(arrayErrors: unknown): boolean {
  return Array.isArray(arrayErrors) && arrayErrors.some(isDefined);
}

function firstKeyValueRowMessage(arrayErrors: unknown): string | undefined {
  if (!Array.isArray(arrayErrors)) return undefined;
  for (const item of arrayErrors) {
    if (!item || typeof item !== 'object') continue;
    const row = item as Record<string, { message?: string } | undefined>;
    const keyMsg = row.key?.message;
    if (keyMsg) return keyMsg;
    const valueMsg = row.value?.message;
    if (valueMsg) return valueMsg;
  }
  return undefined;
}

type KeyValueComboboxPassthrough = Omit<
  ComponentProps<typeof ControlledCombobox>,
  'useControllerProps' | 'items' | 'label'
>;

type KeyValueTextInputPassthrough = Omit<
  ComponentProps<typeof ControlledTextInput>,
  'useControllerProps' | 'label'
>;

export interface MappingFieldsProps<
  TFieldValues extends FieldValues,
  TName extends FieldArrayPath<TFieldValues>,
> {
  control: Control<TFieldValues>;
  /**
   * react-hook-form field array path; each item is `{ key: string; value?: string }`.
   * The UI keeps one trailing blank row; entering text in key or value on that row appends another blank row.
   * Consumers should omit all-blank rows from API payloads (see Transform file submit).
   */
  name: TName;
  /**
   * When true, disables mapping inputs and row removal. Also disabled when the form is disabled
   * (`useForm({ disabled: true })` / `FormProvider`).
   */
  disabled?: boolean;
  /**
   * When set (e.g. file JSON schema), replaces the field array whenever the sorted list of keys changes.
   * Row values are `schemaValueForKey(key)` (default: `{{{key}}}`), matching the file-transform mapping UX.
   * Record values are not used; only keys matter.
   */
  schema?: Record<string, unknown>;
  /** Default value string for each row when syncing from `schema`. Keep stable (e.g. module-level fn) if customized. */
  schemaValueForKey?: (key: string) => string;
  /**
   * Combobox suggestion lists; default key/value options are derived from `schema` keys when present.
   * When a column has no suggestions (empty array and no schema-derived items), that column uses a plain text input instead of a combobox.
   */
  keySuggestions?: string[];
  valueSuggestions?: string[];
  keyColumnLabel?: string;
  valueColumnLabel?: string;
  /** Forward props to the key/value field controls (combobox vs text input is chosen automatically). */
  attributes?: {
    keyCombobox?: Partial<KeyValueComboboxPassthrough>;
    valueCombobox?: Partial<KeyValueComboboxPassthrough>;
    keyTextInput?: Partial<KeyValueTextInputPassthrough>;
    valueTextInput?: Partial<KeyValueTextInputPassthrough>;
  };
}

export const MappingFields = <
  TFieldValues extends FieldValues,
  TName extends FieldArrayPath<TFieldValues>,
>({
  control,
  name,
  disabled,
  schema,
  schemaValueForKey = DEFAULT_SCHEMA_VALUE,
  keySuggestions: keySuggestionsProp,
  valueSuggestions: valueSuggestionsProp,
  keyColumnLabel = 'Key',
  valueColumnLabel = 'Value',
  attributes,
}: MappingFieldsProps<TFieldValues, TName>) => {
  const nameStr = name as string;
  const { errors, disabled: formDisabled } = useFormState<TFieldValues>({ control });
  const isDisabled = Boolean(disabled) || formDisabled;
  const arrayErrors = getAtPath(errors, nameStr);

  const {
    fields: rows,
    append,
    remove,
    replace,
  } = useFieldArray({
    control,
    name,
  });

  const watchedRows = useWatch({
    control,
    name: name as never,
  }) as Array<{ key?: string; value?: string }> | undefined;

  useEffect(() => {
    if (isDisabled) return;
    const list = Array.isArray(watchedRows) ? watchedRows : [];
    if (list.length === 0) {
      append({ key: '', value: '' } as Parameters<typeof append>[0]);
      return;
    }
    if (list.length >= 2) {
      const secondLast = list[list.length - 2];
      const last = list[list.length - 1];
      if (isMappingRowEmpty(secondLast) && isMappingRowEmpty(last)) {
        remove(list.length - 2);
        return;
      }
    }
    const lastRow = list[list.length - 1];
    if (!isMappingRowEmpty(lastRow)) {
      append({ key: '', value: '' } as Parameters<typeof append>[0]);
    }
  }, [append, isDisabled, remove, watchedRows]);

  const schemaKeySignature = useMemo(
    () => (schema ? JSON.stringify(Object.keys(schema).sort()) : ''),
    [schema]
  );

  useEffect(() => {
    if (schema === undefined) return;
    replace([
      ...Object.keys(schema).map((key) => ({
        key,
        value: schemaValueForKey(key),
      })),
      { key: '', value: '' },
    ] as Parameters<typeof replace>[0]);
  }, [replace, schema, schemaKeySignature, schemaValueForKey]);

  const keyOpts = useMemo(
    () => keySuggestionsProp ?? (schema ? Object.keys(schema) : []),
    [keySuggestionsProp, schema]
  );

  const valueOpts = useMemo(
    () =>
      valueSuggestionsProp ??
      (schema ? Object.keys(schema).map((key) => schemaValueForKey(key)) : []),
    [valueSuggestionsProp, schema, schemaValueForKey]
  );

  const useKeyCombobox = keyOpts.length > 0;
  const useValueCombobox = valueOpts.length > 0;

  const {
    formFieldProps: keyComboboxFormFieldProps,
    className: keyComboboxClassName,
    attributes: keyComboboxAttributes,
    ...keyComboboxRest
  } = attributes?.keyCombobox ?? {};

  const {
    formFieldProps: valueComboboxFormFieldProps,
    className: valueComboboxClassName,
    attributes: valueComboboxAttributes,
    ...valueComboboxRest
  } = attributes?.valueCombobox ?? {};

  const {
    formFieldProps: keyTextFormFieldProps,
    className: keyTextClassName,
    hideError: keyTextHideError,
    attributes: keyTextAttributes,
    ...keyTextRest
  } = attributes?.keyTextInput ?? {};

  const {
    formFieldProps: valueTextFormFieldProps,
    className: valueTextClassName,
    hideError: valueTextHideError,
    attributes: valueTextAttributes,
    ...valueTextRest
  } = attributes?.valueTextInput ?? {};

  const firstFieldError = firstKeyValueRowMessage(arrayErrors);

  const renderedRows = useMemo(() => {
    return rows.map((row, index) => (
      <Flex key={row.id} gap="density-lg" align="end" justify="between">
        {useKeyCombobox ? (
          <ControlledCombobox
            {...keyComboboxRest}
            disabled={isDisabled}
            freeForm
            dismissible={false}
            hideError
            className={cn('font-normal', keyComboboxClassName)}
            attributes={keyComboboxAttributes}
            formFieldProps={{
              className: 'min-w-0 flex-1 font-bold',
              ...keyComboboxFormFieldProps,
            }}
            useControllerProps={{ control, name: `${nameStr}.${index}.key`, disabled: isDisabled }}
            items={keyOpts}
            label={index === 0 ? keyColumnLabel : ''}
          />
        ) : (
          <ControlledTextInput
            {...keyTextRest}
            disabled={isDisabled}
            hideError={keyTextHideError ?? true}
            className={keyTextClassName}
            attributes={keyTextAttributes}
            formFieldProps={{
              className: 'min-w-0 flex-1',
              ...keyTextFormFieldProps,
            }}
            useControllerProps={{ control, name: `${nameStr}.${index}.key`, disabled: isDisabled }}
            label={index === 0 ? keyColumnLabel : ''}
          />
        )}
        {useValueCombobox ? (
          <ControlledCombobox
            {...valueComboboxRest}
            disabled={isDisabled}
            freeForm
            dismissible={false}
            hideError
            className={cn('font-normal', valueComboboxClassName)}
            attributes={valueComboboxAttributes}
            formFieldProps={{
              className: 'min-w-0 flex-1 font-bold',
              ...valueComboboxFormFieldProps,
            }}
            useControllerProps={{
              control,
              name: `${nameStr}.${index}.value`,
              disabled: isDisabled,
            }}
            items={valueOpts}
            label={index === 0 ? valueColumnLabel : ''}
          />
        ) : (
          <ControlledTextInput
            {...valueTextRest}
            disabled={isDisabled}
            hideError={valueTextHideError ?? true}
            className={valueTextClassName}
            attributes={valueTextAttributes}
            formFieldProps={{
              className: 'min-w-0 flex-1',
              ...valueTextFormFieldProps,
            }}
            useControllerProps={{
              control,
              name: `${nameStr}.${index}.value`,
              disabled: isDisabled,
            }}
            label={index === 0 ? valueColumnLabel : ''}
          />
        )}
        <Button
          type="button"
          kind="tertiary"
          aria-label="Remove row"
          disabled={isDisabled || index === rows.length - 1}
          onClick={() => {
            remove(index);
          }}
        >
          <Trash />
        </Button>
      </Flex>
    ));
  }, [
    rows,
    control,
    remove,
    keyOpts,
    valueOpts,
    nameStr,
    keyColumnLabel,
    valueColumnLabel,
    useKeyCombobox,
    useValueCombobox,
    keyComboboxRest,
    keyComboboxClassName,
    keyComboboxFormFieldProps,
    keyComboboxAttributes,
    valueComboboxRest,
    valueComboboxClassName,
    valueComboboxFormFieldProps,
    valueComboboxAttributes,
    keyTextRest,
    keyTextClassName,
    keyTextFormFieldProps,
    keyTextAttributes,
    keyTextHideError,
    valueTextRest,
    valueTextClassName,
    valueTextFormFieldProps,
    valueTextAttributes,
    valueTextHideError,
    isDisabled,
  ]);

  return (
    <Stack gap="density-lg">
      <Stack gap="density-lg">{renderedRows}</Stack>
      {fieldArrayHasErrors(arrayErrors) ? (
        <Banner
          kind="inline"
          status="warning"
          attributes={{ BannerIcon: { className: 'self-start' } }}
        >
          {firstFieldError}
        </Banner>
      ) : null}
    </Stack>
  );
};
