// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { SegmentedControl } from '@nvidia/foundations-react-core';
import { MessageSquareText } from 'lucide-react';
import type { FC, KeyboardEvent, MouseEvent } from 'react';

export const SpanPayloadViewMode = {
  chat: 'chat',
  raw: 'raw',
  markdown: 'markdown',
  json: 'json',
} as const;

export type SpanPayloadViewMode = (typeof SpanPayloadViewMode)[keyof typeof SpanPayloadViewMode];

const VIEW_MODE_VALUES: SpanPayloadViewMode[] = Object.values(SpanPayloadViewMode);
const VIEW_MODES: ReadonlySet<string> = new Set(VIEW_MODE_VALUES);

const isSpanPayloadViewMode = (value: string): value is SpanPayloadViewMode =>
  VIEW_MODES.has(value);

const VIEW_MODE_ITEMS = [
  {
    value: SpanPayloadViewMode.chat,
    'aria-label': 'Chat',
    children: (
      <span className="flex items-center" title="Chat messages">
        <MessageSquareText size={14} aria-hidden />
        <span className="sr-only">Chat</span>
      </span>
    ),
  },
  { value: SpanPayloadViewMode.raw, children: 'raw' },
  { value: SpanPayloadViewMode.markdown, children: 'md' },
  { value: SpanPayloadViewMode.json, children: 'json' },
];

interface SpanPayloadRendererControlProps {
  sectionLabel: string;
  value: SpanPayloadViewMode;
  onValueChange: (value: SpanPayloadViewMode) => void;
}

/** Rendering-style selector shown in an Input/Output accordion trigger. */
export const SpanPayloadRendererControl: FC<SpanPayloadRendererControlProps> = ({
  sectionLabel,
  value,
  onValueChange,
}) => {
  // The selector lives inside an accordion <summary>. Keep its mouse and
  // keyboard interactions from also toggling the surrounding section. A
  // <summary> still toggles for clicks on its radio descendants, so selection
  // is applied explicitly before canceling that default action.
  const stopAccordionToggle = (event: MouseEvent<HTMLDivElement>): void => {
    event.preventDefault();
    event.stopPropagation();

    const target = event.target instanceof Element ? event.target : null;
    const input =
      target instanceof HTMLInputElement
        ? target
        : target?.closest('label')?.querySelector<HTMLInputElement>('input[type="radio"]');
    if (input && isSpanPayloadViewMode(input.value) && input.value !== value) {
      const nextValue = input.value;
      // A canceled native radio click restores the previous checked state after
      // React's event handlers finish. Apply the controlled value immediately
      // after that restoration so the DOM and React state stay in sync.
      queueMicrotask(() => onValueChange(nextValue));
    }
  };
  const stopKeyboardPropagation = (event: KeyboardEvent<HTMLDivElement>): void => {
    event.stopPropagation();

    const input = event.target instanceof HTMLInputElement ? event.target : null;
    if (!input || !isSpanPayloadViewMode(input.value)) return;

    const currentIndex = VIEW_MODE_VALUES.indexOf(input.value);
    let nextIndex: number | null = null;
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
      nextIndex = (currentIndex + 1) % VIEW_MODE_VALUES.length;
    } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
      nextIndex = (currentIndex - 1 + VIEW_MODE_VALUES.length) % VIEW_MODE_VALUES.length;
    } else if (event.key === 'Home') {
      nextIndex = 0;
    } else if (event.key === 'End') {
      nextIndex = VIEW_MODE_VALUES.length - 1;
    }

    if (nextIndex === null) return;
    event.preventDefault();
    const nextValue = VIEW_MODE_VALUES[nextIndex];
    if (!nextValue) return;
    const container = event.currentTarget;
    queueMicrotask(() => {
      onValueChange(nextValue);
      container.querySelector<HTMLInputElement>(`input[value="${nextValue}"]`)?.focus();
    });
  };

  return (
    <SegmentedControl
      aria-label={`${sectionLabel} rendering style`}
      size="tiny"
      value={value}
      items={VIEW_MODE_ITEMS}
      onClickCapture={stopAccordionToggle}
      onKeyDown={stopKeyboardPropagation}
    />
  );
};
