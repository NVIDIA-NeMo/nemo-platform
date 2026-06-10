// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  Button,
  DropdownContent,
  DropdownHeading,
  DropdownItem,
  DropdownRoot,
  DropdownSection,
  DropdownTrigger,
  Flex,
  Stack,
  Text,
} from '@nvidia/foundations-react-core';
import { ChevronDown, Database, Upload, X } from 'lucide-react';
import { type FC, useMemo, useState } from 'react';

export interface DatasetDropdownOption {
  value: string;
  label: string;
}

interface DatasetDropdownProps {
  /** Selectable dataset options (sample datasets plus an optional uploaded entry). */
  datasets: DatasetDropdownOption[];
  /** Currently selected value, or undefined when nothing is selected. */
  value: string | undefined;
  onValueChange: (value: string) => void;
  /** Fired when the user picks the "Upload Dataset" action row. */
  onUpload: () => void;
  /** When provided, a clear (X) control is shown in the trigger once a dataset is selected. */
  onClear?: () => void;
  placeholder?: string;
  disabled?: boolean;
  size?: 'small' | 'medium' | 'large';
  className?: string;
}

/**
 * Dataset picker that reuses the model select trigger pattern
 * (`ModelSelectV2`/`ModelDropdown`) so the two pickers look identical. The only
 * differences are the leading icon (a generic `Database` instead of a model
 * creator icon) and that the list is a flat set of dataset options plus an
 * "Upload Dataset" action row.
 */
export const DatasetDropdown: FC<DatasetDropdownProps> = ({
  datasets,
  value,
  onValueChange,
  onUpload,
  onClear,
  placeholder = 'Select a dataset...',
  disabled = false,
  size = 'small',
  className,
}) => {
  const [open, setOpen] = useState(false);

  const selected = useMemo(() => datasets.find((d) => d.value === value), [datasets, value]);

  const triggerLabel = selected ? selected.label : placeholder;
  const triggerTextKind = size === 'small' ? 'label/regular/sm' : 'label/regular/md';

  const handleSelect = (next: string) => {
    onValueChange(next);
    setOpen(false);
  };

  const handleUpload = () => {
    onUpload();
    setOpen(false);
  };

  return (
    <DropdownRoot open={open} onOpenChange={setOpen}>
      <DropdownTrigger asChild showChevron={false} className={className}>
        <Button
          kind="secondary"
          size={size}
          disabled={disabled}
          aria-label="Select a dataset"
          data-testid="dataset-dropdown-trigger"
          className="overflow-hidden !border-[var(--border-color-interaction-base)] !bg-[var(--background-color-interaction-base)] hover:!border-[var(--border-color-interaction-hover)] [&[data-state=open]]:!border-[var(--border-color-interaction-selected)]"
        >
          <Flex align="center" gap="density-sm" className="min-w-0 w-full justify-between">
            <Flex align="center" gap="density-sm" className="min-w-0 flex-1">
              {selected && <Database size={16} className="text-base flex-shrink-0" />}
              <Text kind={triggerTextKind} className="truncate">
                {triggerLabel}
              </Text>
            </Flex>
            <Flex align="center" gap="density-sm" className="flex-shrink-0">
              {selected && onClear && !disabled && (
                <span
                  role="button"
                  tabIndex={0}
                  aria-label="Clear selected dataset"
                  className="flex cursor-pointer items-center rounded p-0.5 text-subtle hover:text-base"
                  onPointerDown={(e) => {
                    // Prevent the trigger from opening the dropdown on this click.
                    e.preventDefault();
                    e.stopPropagation();
                  }}
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    onClear();
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      e.stopPropagation();
                      onClear();
                    }
                  }}
                >
                  <X size={16} />
                </span>
              )}
              <ChevronDown
                size={16}
                className={`transition-transform ${open ? 'rotate-180' : ''}`}
              />
            </Flex>
          </Flex>
        </Button>
      </DropdownTrigger>
      <DropdownContent
        align="start"
        side="bottom"
        data-testid="dataset-dropdown-content"
        className="min-w-[320px]"
        style={{ width: 320 }} // eslint-disable-line no-restricted-syntax -- KUI DropdownContent needs explicit width
      >
        <Stack className="overflow-auto max-h-[300px] w-full">
          <DropdownSection>
            <DropdownHeading>Datasets available</DropdownHeading>
            {datasets.map((dataset) => (
              <DropdownItem key={dataset.value} onSelect={() => handleSelect(dataset.value)}>
                <Flex align="center" gap="density-sm" className="min-w-0">
                  <Database size={16} className="text-base flex-shrink-0" />
                  <Text className="truncate">{dataset.label}</Text>
                </Flex>
              </DropdownItem>
            ))}
          </DropdownSection>
        </Stack>
        <div className="border-base border-t flex items-center w-full">
          <DropdownItem onSelect={handleUpload}>
            <Flex align="center" gap="density-sm">
              <Upload size={16} className="flex-shrink-0" />
              <Text>Upload Dataset</Text>
            </Flex>
          </DropdownItem>
        </div>
      </DropdownContent>
    </DropdownRoot>
  );
};
