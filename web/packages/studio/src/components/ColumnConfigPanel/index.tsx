// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { SamplerType } from '@nemo/sdk/generated/data-designer/schema';
import {
  Banner,
  Button,
  Flex,
  FormField,
  SelectContent,
  SelectItem,
  SelectListbox,
  SelectRoot,
  SelectTrigger,
  Stack,
  Switch,
  Text,
  TextArea,
  TextInput,
} from '@nvidia/foundations-react-core';
import { ICON_COLOR_CLASS } from '@studio/components/AddColumnPalette/constants';
import { CardIconBadge } from '@studio/components/common/SelectableCard';
import {
  type BuilderColumn,
  type ColumnField,
  getColumnFields,
  validateColumnName,
} from '@studio/routes/DataDesignerJobBuildRoute/columns';
import { Trash2, X } from 'lucide-react';
import type { FC } from 'react';

/** Renders one config field as the appropriate control, wrapped in a `FormField`. */
const FieldControl: FC<{
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
      case 'number':
        return (
          <TextInput
            value={value}
            onValueChange={onChange}
            placeholder={field.placeholder}
            attributes={{ Input: { type: 'number', inputMode: 'decimal' } }}
          />
        );
      default:
        return <TextInput value={value} onValueChange={onChange} placeholder={field.placeholder} />;
    }
  };

  // A boolean toggle reads better as an inline switch than a stacked FormField control.
  if (field.kind === 'switch') {
    return (
      <FormField slotLabel={field.label} slotInfo={field.helperText}>
        <Switch
          checked={value === 'true'}
          onCheckedChange={(checked) => onChange(checked ? 'true' : 'false')}
        />
      </FormField>
    );
  }

  return (
    <FormField slotLabel={field.label} required={field.required} slotInfo={field.helperText}>
      {control()}
    </FormField>
  );
};

export interface ColumnConfigPanelProps {
  /** The column currently being edited. */
  column: BuilderColumn;
  /** Names used by other columns, for the uniqueness check. */
  takenNames: Set<string>;
  /** Fired live as the user edits the name or any field. */
  onChange: (patch: { name?: string; values?: Record<string, string> }) => void;
  /** Removes this column from the canvas. */
  onRemove: () => void;
  /** Closes the panel (deselects the column). */
  onClose: () => void;
}

/**
 * Setup note shown for the managed `person` sampler. Unlike the other samplers, it reads
 * from downloaded Nemotron Personas datasets, so it fails at preview/build time (with
 * "Failed to access Nemotron personas filesets") until those are available for the locale.
 */
const PersonSamplerNote: FC = () => (
  <Banner kind="inline" status="info" title="Requires a managed dataset">
    <Text kind="body/regular/sm">
      The person sampler reads from downloaded Nemotron Personas datasets. Before it can preview or
      build:
    </Text>
    <ol className="list-decimal pl-density-lg">
      <li>
        Download the Nemotron Personas dataset for your locale into the Data Designer service's
        managed assets directory.
      </li>
      <li>
        Set <Text kind="body/bold/sm">Locale</Text> below to a supported value (e.g. en_US, en_IN,
        fr_FR, ja_JP, ko_KR, pt_BR).
      </li>
    </ol>
    <Text kind="body/regular/sm">
      Without the managed dataset, use a different sampler for local previews.
    </Text>
  </Banner>
);

/**
 * Right-hand config panel for the selected column on the build canvas.
 *
 * Renders as an inline pane (not an overlay) so the canvas stays visible while editing.
 * Edits are applied live via {@link ColumnConfigPanelProps.onChange} — as the user types
 * Jinja2 `{{ column_name }}` references, the canvas re-derives its dependency edges. The
 * fields shown are derived from the column type via {@link getColumnFields}.
 */
export const ColumnConfigPanel: FC<ColumnConfigPanelProps> = ({
  column,
  takenNames,
  onChange,
  onRemove,
  onClose,
}) => {
  const { option, name, values } = column;
  const { icon: Icon, label, description, color } = option;
  const fields = getColumnFields(option);
  const nameError = validateColumnName(name, takenNames);

  const setValue = (key: string, value: string) =>
    onChange({ values: { ...values, [key]: value } });

  return (
    <aside
      aria-label={`Configure ${label} column`}
      className="flex h-full w-full flex-col bg-surface-base"
    >
      <Flex
        align="start"
        justify="between"
        gap="density-md"
        className="shrink-0 border-b border-base p-density-lg"
      >
        <Flex align="center" gap="density-sm" className="min-w-0">
          <CardIconBadge>
            <Icon size={16} className={ICON_COLOR_CLASS[color]} aria-hidden />
          </CardIconBadge>
          <Stack gap="density-xxs" className="min-w-0">
            <Text kind="body/bold/md" className="truncate">
              {label}
            </Text>
            <Text kind="body/regular/xs" className="text-secondary truncate">
              {description}
            </Text>
          </Stack>
        </Flex>
        <Button
          kind="tertiary"
          color="neutral"
          size="small"
          aria-label="Close column config"
          onClick={onClose}
        >
          <X size={16} aria-hidden />
        </Button>
      </Flex>

      <Stack gap="density-lg" padding="density-lg" className="min-h-0 flex-1 overflow-y-auto">
        {option.samplerType === SamplerType.person && <PersonSamplerNote />}
        <FormField
          slotLabel="Column name"
          required
          slotInfo="Other columns reference this via {{ name }}."
          status={name && nameError ? 'error' : undefined}
          slotError={name ? (nameError ?? undefined) : undefined}
        >
          <TextInput
            value={name}
            onValueChange={(value) => onChange({ name: value })}
            placeholder="e.g. topic"
            attributes={{ Input: { 'aria-label': 'Column name' } }}
          />
        </FormField>

        {fields.map((field) => (
          <FieldControl
            key={field.key}
            field={field}
            value={values[field.key] ?? ''}
            onChange={(value) => setValue(field.key, value)}
          />
        ))}
      </Stack>

      <Flex align="center" justify="start" className="shrink-0 border-t border-base p-density-lg">
        <Button kind="tertiary" color="danger" size="small" onClick={onRemove}>
          <Trash2 size={16} aria-hidden />
          Remove column
        </Button>
      </Flex>
    </aside>
  );
};
