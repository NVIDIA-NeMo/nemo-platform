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
  /** Optional DOM id for the item element (e.g. to scroll it into view). */
  id?: string;
  /** Leading trigger content (e.g. name + badge). Grows to fill the row. */
  slotLabel: ReactNode;
  /** Trailing trigger content pinned to the right (e.g. metrics + actions). The
   * trigger is a `<summary>`, so interactive controls here must stop the click
   * from toggling the row (see `SpanFeedbackControls`). */
  slotEnd?: ReactNode;
  /** Body revealed when the item is open. */
  slotContent: ReactNode;
  disabled?: boolean;
}

interface IntakeAccordionProps {
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

// KUI's accordion paints its own surface and uses heavier paddings than the
// dense intake design wants. Every styleable property reads a `--nv-*` variable
// (e.g. `padding: var(--nv-accordion-trigger-padding, …)`), so we override by
// setting those variables on the root — they inherit down to the trigger/content
// elements that read them, winning without any cascade fight. Only the flex
// layout of KUI's internal `.nv-accordion-label-text` wrapper (which has no
// variable and no exposed className) is left to IntakeAccordion.css.
const VARIANT_VARS: Record<NonNullable<IntakeAccordionProps['variant']>, string> = {
  row: '[--nv-accordion-root-bg:transparent] [--nv-accordion-trigger-padding:var(--spacing-density-md)_var(--spacing-density-lg)] [--nv-accordion-content-padding:var(--spacing-density-lg)]',
  section:
    '[--nv-accordion-root-bg:transparent] [--nv-accordion-trigger-padding:var(--spacing-density-sm)_0] [--nv-accordion-content-padding:var(--spacing-density-lg)_0]',
};

/**
 * Studio-styled accordion for the intake trace/span views. Wraps the KUI
 * Accordion primitives so it follows the same composition and a11y conventions
 * while matching the Experiments design. Always multi-open, since every intake
 * usage allows several sections open at once.
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
    className={`intake-accordion ${VARIANT_VARS[variant]} ${className ?? ''}`}
  >
    {items.map((item, index) => (
      <AccordionItem
        key={item.value}
        id={item.id}
        value={item.value}
        disabled={item.disabled}
        // KUI gives every item a border-bottom; drop it on the last row so the
        // list doesn't double up with its container border.
        className={
          variant === 'row' && index === items.length - 1 ? '[--nv-accordion-item-border:0]' : ''
        }
      >
        <AccordionTrigger chevronPosition="start" disabled={item.disabled}>
          {/* Wrappers are `div`s, not `span`s: callers pass arbitrary ReactNode
              (including block-level content such as `Flex`), which is invalid DOM
              nested inside an inline `span`. */}
          <div className="flex flex-1 items-center gap-[var(--spacing-density-sm)] min-w-0">
            {item.slotLabel}
          </div>
          {item.slotEnd ? (
            <div className="flex shrink-0 items-center gap-[var(--spacing-density-lg)]">
              {item.slotEnd}
            </div>
          ) : null}
        </AccordionTrigger>
        <AccordionContent>{item.slotContent}</AccordionContent>
      </AccordionItem>
    ))}
  </AccordionRoot>
);
