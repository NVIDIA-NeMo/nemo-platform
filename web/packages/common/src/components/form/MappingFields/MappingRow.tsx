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
import type {
  KeyValueComboboxPassthrough,
  KeyValueTextInputPassthrough,
} from '@nemo/common/src/components/form/MappingFields/types';
import { Button, Grid, Text } from '@nvidia/foundations-react-core';
import cn from 'classnames';
import { Trash } from 'lucide-react';
import { memo, ReactNode } from 'react';
import { Control, FieldValues } from 'react-hook-form';

interface Props<TFieldValues extends FieldValues> {
  control: Control<TFieldValues>;
  /** Field array path, e.g. `mappings`. */
  name: string;
  index: number;
  /** The trailing draft row cannot be removed. */
  isLastRow: boolean;
  isDisabled: boolean;
  keyOpts: string[];
  valueOpts: string[];
  keyColumnLabel: string;
  valueColumnLabel: string;
  /** Popover content for the column header info icons; only the labelled first row shows them. */
  keyColumnInfo?: ReactNode;
  valueColumnInfo?: ReactNode;
  /** Help text for this row's key, rendered beneath the inputs. */
  description?: string;
  keyCombobox: Partial<KeyValueComboboxPassthrough>;
  valueCombobox: Partial<KeyValueComboboxPassthrough>;
  keyTextInput: Partial<KeyValueTextInputPassthrough>;
  valueTextInput: Partial<KeyValueTextInputPassthrough>;
  onRemove: (index: number) => void;
}

const MappingRowInner = <TFieldValues extends FieldValues>({
  control,
  name,
  index,
  isLastRow,
  isDisabled,
  keyOpts,
  valueOpts,
  keyColumnLabel,
  valueColumnLabel,
  keyColumnInfo,
  valueColumnInfo,
  description,
  keyCombobox,
  valueCombobox,
  keyTextInput,
  valueTextInput,
  onRemove,
}: Props<TFieldValues>) => {
  const {
    formFieldProps: keyComboboxFormFieldProps,
    className: keyComboboxClassName,
    attributes: keyComboboxAttributes,
    ...keyComboboxRest
  } = keyCombobox;

  const {
    formFieldProps: valueComboboxFormFieldProps,
    className: valueComboboxClassName,
    attributes: valueComboboxAttributes,
    ...valueComboboxRest
  } = valueCombobox;

  const {
    formFieldProps: keyTextFormFieldProps,
    className: keyTextClassName,
    hideError: keyTextHideError,
    attributes: keyTextAttributes,
    ...keyTextRest
  } = keyTextInput;

  const {
    formFieldProps: valueTextFormFieldProps,
    className: valueTextClassName,
    hideError: valueTextHideError,
    attributes: valueTextAttributes,
    ...valueTextRest
  } = valueTextInput;

  /** Only the first row carries the column labels, and with them the info popovers. */
  const isHeaderRow = index === 0;

  return (
    <Grid className="grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] items-end gap-x-density-lg gap-y-density-xs">
      {keyOpts.length > 0 ? (
        <ControlledCombobox
          {...keyComboboxRest}
          disabled={isDisabled}
          freeForm
          dismissible={false}
          hideError
          className={cn('font-normal', keyComboboxClassName)}
          attributes={keyComboboxAttributes}
          formFieldProps={{
            className: 'min-w-0 font-bold',
            slotInfo: isHeaderRow ? keyColumnInfo : undefined,
            ...keyComboboxFormFieldProps,
          }}
          useControllerProps={{ control, name: `${name}.${index}.key`, disabled: isDisabled }}
          items={keyOpts}
          label={isHeaderRow ? keyColumnLabel : ''}
        />
      ) : (
        <ControlledTextInput
          {...keyTextRest}
          disabled={isDisabled}
          hideError={keyTextHideError ?? true}
          className={keyTextClassName}
          attributes={keyTextAttributes}
          formFieldProps={{
            className: 'min-w-0',
            slotInfo: isHeaderRow ? keyColumnInfo : undefined,
            ...keyTextFormFieldProps,
          }}
          useControllerProps={{ control, name: `${name}.${index}.key`, disabled: isDisabled }}
          label={isHeaderRow ? keyColumnLabel : ''}
        />
      )}
      {valueOpts.length > 0 ? (
        <ControlledCombobox
          {...valueComboboxRest}
          disabled={isDisabled}
          freeForm
          dismissible={false}
          hideError
          className={cn('font-normal', valueComboboxClassName)}
          attributes={valueComboboxAttributes}
          formFieldProps={{
            className: 'min-w-0 font-bold',
            slotInfo: isHeaderRow ? valueColumnInfo : undefined,
            ...valueComboboxFormFieldProps,
          }}
          useControllerProps={{ control, name: `${name}.${index}.value`, disabled: isDisabled }}
          items={valueOpts}
          label={isHeaderRow ? valueColumnLabel : ''}
        />
      ) : (
        <ControlledTextInput
          {...valueTextRest}
          disabled={isDisabled}
          hideError={valueTextHideError ?? true}
          className={valueTextClassName}
          attributes={valueTextAttributes}
          formFieldProps={{
            className: 'min-w-0',
            slotInfo: isHeaderRow ? valueColumnInfo : undefined,
            ...valueTextFormFieldProps,
          }}
          useControllerProps={{ control, name: `${name}.${index}.value`, disabled: isDisabled }}
          label={isHeaderRow ? valueColumnLabel : ''}
        />
      )}
      <Button
        type="button"
        kind="tertiary"
        aria-label="Remove row"
        disabled={isDisabled || isLastRow}
        onClick={() => {
          onRemove(index);
        }}
      >
        <Trash />
      </Button>
      {description ? (
        <Text className="col-start-1 col-end-2 text-secondary">{description}</Text>
      ) : null}
    </Grid>
  );
};

/**
 * Memoized so that typing in one row (which re-renders the field array via `useWatch`)
 * does not re-render every other row's combobox.
 */
export const MappingRow = memo(MappingRowInner) as typeof MappingRowInner;
