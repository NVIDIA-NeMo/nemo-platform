// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import '@nemo/common/src/components/IntakeAccordion/IntakeAccordion.css';
import {
  AccordionContent,
  AccordionItem,
  AccordionRoot,
  AccordionTrigger,
} from '@nvidia/foundations-react-core';
import type { FC, ReactNode } from 'react';

export interface IntakeAccordionItem {
  /** Stable identifier used to track the open/closed state of the item. */
  value: string;
  /** Leading trigger content (e.g. name + badge). Grows to fill the row. */
  slotLabel: ReactNode;
  /** Trailing trigger content pinned to the right (e.g. metrics + actions). */
  slotEnd?: ReactNode;
  /** Body revealed when the item is open. */
  slotContent: ReactNode;
  disabled?: boolean;
}

export interface IntakeAccordionProps {
  items: IntakeAccordionItem[];
  /**
   * `row` (default) renders a dense, bordered list — used for the span
   * hierarchy. `section` renders lighter, label-led sections — used for the
   * metadata groups nested inside a span.
   */
  variant?: 'row' | 'section';
  /** Controlled open items. Pair with `onValueChange`. */
  value?: string[];
  /** Initial open items for uncontrolled usage. */
  defaultValue?: string[];
  onValueChange?: (value: string[]) => void;
  className?: string;
}

/**
 * Studio-styled accordion for the intake trace/span views. Wraps the KUI
 * Accordion primitives so it follows the same composition and a11y conventions
 * while matching the Experiments design (see IntakeAccordion.css). Always
 * multi-open, since every intake usage allows several sections open at once.
 */
export const IntakeAccordion: FC<IntakeAccordionProps> = ({
  items,
  variant = 'row',
  value,
  defaultValue,
  onValueChange,
  className,
}) => (
  <AccordionRoot
    multiple
    value={value}
    defaultValue={defaultValue}
    onValueChange={onValueChange}
    className={`intake-accordion intake-accordion--${variant} ${className ?? ''}`}
  >
    {items.map((item) => (
      <AccordionItem
        key={item.value}
        value={item.value}
        disabled={item.disabled}
        className="intake-accordion-item"
      >
        <AccordionTrigger
          chevronPosition="start"
          disabled={item.disabled}
          className="intake-accordion-trigger"
        >
          <span className="intake-accordion-label">{item.slotLabel}</span>
          {item.slotEnd ? <span className="intake-accordion-end">{item.slotEnd}</span> : null}
        </AccordionTrigger>
        <AccordionContent className="intake-accordion-content">{item.slotContent}</AccordionContent>
      </AccordionItem>
    ))}
  </AccordionRoot>
);
