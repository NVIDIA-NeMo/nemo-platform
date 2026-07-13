// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  FormField,
  SelectContent,
  SelectItem,
  SelectListbox,
  SelectRoot,
  SelectTrigger,
  TextArea,
  TextInput,
} from '@nvidia/foundations-react-core';
import type { ColumnField } from '@studio/routes/DataDesignerJobBuildRoute/columns';
import type { FC } from 'react';

export const FieldControl: FC<{
  field: ColumnField;
  value: string;
  onChange: (value: string) => void;
}> = ({ field, value, onChange }) => {
  const control = () => {
    switch (field.kind) {
      case 'textarea':
        return (
          <TextArea
            value={value}
            onValueChange={onChange}
            placeholder={field.placeholder}
            resizeable="auto"
          />
        );
      case 'select':
        return (
          <SelectRoot value={value || undefined} onValueChange={onChange}>
            <SelectTrigger className="w-full" placeholder="Select…" />
            <SelectContent className="w-(--radix-popper-anchor-width)">
              <SelectListbox>
                {field.options?.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectListbox>
            </SelectContent>
          </SelectRoot>
        );
      default:
        return <TextInput value={value} onValueChange={onChange} placeholder={field.placeholder} />;
    }
  };

  return (
    <FormField slotLabel={field.label} required={field.required} slotInfo={field.helperText}>
      {control()}
    </FormField>
  );
};
