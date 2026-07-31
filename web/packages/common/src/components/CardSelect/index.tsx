// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Card, Flex, Text } from '@nvidia/foundations-react-core';
import type { FC } from 'react';

export interface CardSelectOption {
  /** Value reported to `onChange`; also the React key. */
  value: string;
  /** Title text displayed prominently in the card. */
  title: string;
  /** Optional description text displayed below the title. */
  description?: string;
}

export interface CardSelectProps {
  /** Card options to render. */
  options: CardSelectOption[];
  /** Currently selected option value. */
  value?: string;
  /** Fired with the option's value when a card is chosen. */
  onChange: (value: string) => void;
  /** Accessible name for the group of cards. */
  label?: string;
  /** Direction to stack cards. Defaults to "row" (horizontal). */
  direction?: 'row' | 'col';
  className?: string;
}

/**
 * A row (or column) of selectable cards — a visual stand-in for a radio group when the
 * choices deserve more explanation than a dropdown row affords. No radio dot is drawn;
 * selection is conveyed by the card's own selected treatment.
 *
 * Each card renders `asChild` as a native `<button>`, which is what makes it reachable by
 * keyboard and announced with its pressed state. KUI's guidance is that an interactive
 * Card is a single click target, so do not place buttons or links inside an option.
 *
 * @example
 * ```tsx
 * <CardSelect
 *   label="Eval config"
 *   value={configKey}
 *   onChange={setConfigKey}
 *   options={[
 *     { value: 'task_driven', title: 'Task-Driven', description: '...' },
 *     { value: 'dataset_driven', title: 'Dataset-Driven', description: '...' },
 *   ]}
 * />
 * ```
 */
export const CardSelect: FC<CardSelectProps> = ({
  options,
  value,
  onChange,
  label,
  direction = 'row',
  className,
}) => (
  <Flex
    gap="density-md"
    direction={direction}
    className={className}
    role="group"
    aria-label={label}
  >
    {options.map((option) => {
      const selected = option.value === value;
      return (
        <Card
          key={option.value}
          asChild
          interactive
          selected={selected}
          className="flex-1 cursor-pointer text-left shadow-none!"
        >
          <button type="button" aria-pressed={selected} onClick={() => onChange(option.value)}>
            <Flex gap="density-sm" direction="col" align="start" className="h-full">
              <Text kind="label/bold/lg">{option.title}</Text>
              {option.description && <Text kind="body/regular/md">{option.description}</Text>}
            </Flex>
          </button>
        </Card>
      );
    })}
  </Flex>
);
