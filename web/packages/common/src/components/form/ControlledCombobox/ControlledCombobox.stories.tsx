/*
 * SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 *
 * NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
 * property and proprietary rights in and to this material, related
 * documentation and any modifications thereto. Any use, reproduction,
 * disclosure or distribution of this material and related documentation
 * without an express license agreement from NVIDIA CORPORATION or
 * its affiliates is strictly prohibited.
 */

import { ControlledCombobox } from '@nemo/common/src/components/form/ControlledCombobox/index';
import { Stack, Text } from '@nvidia/foundations-react-core';
import type { Meta, StoryObj } from '@storybook/react';
import { useState } from 'react';
import { FormProvider, useForm } from 'react-hook-form';

const LABELS = ['email', 'phone_number', 'first_name', 'last_name', 'ssn', 'street_address'];

const SECTIONED = [
  {
    kind: 'section' as const,
    slotHeading: 'Personal Identity',
    items: ['first_name', 'last_name'],
  },
  { kind: 'section' as const, slotHeading: 'Contact', items: ['email', 'phone_number'] },
];

interface StoryForm {
  single: string;
  multiple: string[];
}

interface HarnessProps {
  kind?: 'single' | 'multiple';
  items?: React.ComponentProps<typeof ControlledCombobox>['items'];
  freeForm?: boolean;
  loading?: boolean;
  disabled?: boolean;
  placeholder?: string;
  multipleMode?: 'tags' | 'count';
  /** Mirrors how a caller drives the search text to offer entries that aren't in `items`. */
  offerTypedValue?: boolean;
  defaultValues?: Partial<StoryForm>;
}

function ControlledComboboxHarness({
  kind = 'single',
  items = LABELS,
  offerTypedValue = false,
  defaultValues,
  ...comboboxProps
}: HarnessProps) {
  const methods = useForm<StoryForm>({
    defaultValues: { single: '', multiple: [], ...defaultValues },
    mode: 'onChange',
  });
  const [inputValue, setInputValue] = useState('');
  const name = kind === 'multiple' ? 'multiple' : 'single';
  const value = methods.watch(name);

  const selected = Array.isArray(value) ? value : [];
  const typed = inputValue.trim();
  const offered = (items ?? []).flatMap((item) =>
    typeof item === 'string' ? [item] : 'items' in item ? item.items : []
  );
  const showTyped =
    offerTypedValue && typed && !offered.includes(typed) && !selected.includes(typed);
  const resolvedItems = showTyped
    ? [{ kind: 'section' as const, slotHeading: 'Custom', items: [typed] }, ...(items as [])]
    : items;

  return (
    <FormProvider {...methods}>
      <Stack gap="density-xl" className="max-w-md">
        <ControlledCombobox
          {...comboboxProps}
          kind={kind}
          items={resolvedItems}
          aria-label="Labels"
          {...(offerTypedValue ? { inputValue, onInputValueChange: setInputValue } : {})}
          onChange={() => setInputValue('')}
          useControllerProps={{ name, control: methods.control }}
          formFieldProps={{ slotLabel: 'Entity labels' }}
        />
        <Stack
          gap="density-sm"
          className="rounded-md border border-[var(--border-subtle-1)] p-density-md"
        >
          <Text kind="body/bold/sm">Live values (Dev only)</Text>
          <pre className="overflow-auto text-xs whitespace-pre-wrap font-mono opacity-90">
            {JSON.stringify({ value, inputValue }, null, 2)}
          </pre>
        </Stack>
      </Stack>
    </FormProvider>
  );
}

const meta: Meta<typeof ControlledComboboxHarness> = {
  component: ControlledComboboxHarness,
  title: 'Studio Common/ControlledCombobox',
  decorators: [
    (Story) => (
      <div className="p-density-lg">
        <Story />
      </div>
    ),
  ],
};

export default meta;

type Story = StoryObj<typeof ControlledComboboxHarness>;

export const Single: Story = {
  name: 'Single select',
  args: {},
};

export const SingleFreeForm: Story = {
  name: 'Single select (freeForm)',
  args: { freeForm: true, placeholder: 'Type anything...' },
};

export const Multiple: Story = {
  name: 'Multi select',
  args: { kind: 'multiple', defaultValues: { multiple: ['email'] } },
};

export const MultipleCountSummary: Story = {
  name: 'Multi select (count summary)',
  args: {
    kind: 'multiple',
    multipleMode: 'count',
    placeholder: 'Select labels...',
    defaultValues: { multiple: ['email', 'ssn'] },
  },
};

export const MultipleSectioned: Story = {
  name: 'Multi select (sectioned items)',
  args: { kind: 'multiple', items: SECTIONED },
};

export const MultipleFreeForm: Story = {
  name: 'Multi select (freeForm, adds on Enter)',
  args: { kind: 'multiple', freeForm: true, placeholder: 'Type a label, then Enter...' },
};

export const MultipleCustomEntries: Story = {
  name: 'Multi select (custom entries)',
  args: {
    kind: 'multiple',
    offerTypedValue: true,
    items: SECTIONED,
    multipleMode: 'count',
    placeholder: 'Select or type a label...',
  },
};

export const Loading: Story = {
  args: { loading: true, items: [] },
};

export const Disabled: Story = {
  args: { disabled: true, defaultValues: { single: 'email' } },
};
