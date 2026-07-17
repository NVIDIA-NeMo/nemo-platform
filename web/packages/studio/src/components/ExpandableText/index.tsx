// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Stack, Text } from '@nvidia/foundations-react-core';
import { type FC, useLayoutEffect, useRef, useState } from 'react';

// Static classes so Tailwind keeps them; `line-clamp-${n}` would be purged.
const CLAMP_CLASS: Record<number, string> = { 2: 'line-clamp-2', 3: 'line-clamp-3' };

interface ExpandableTextProps {
  /** The text to render; truncated until expanded. */
  text: string;
  /** Lines shown before truncation (ignored when `fill` is set). Defaults to 3. */
  lines?: 2 | 3;
  /**
   * Clamp to the parent's available height (showing as many lines as fit) instead of a fixed line
   * count. Requires the parent to be a flex column with a bounded height so this can grow into it.
   */
  fill?: boolean;
}

/**
 * Body text truncated with a "+ View more" / "- View less" toggle that appears only when the text
 * actually overflows. In `fill` mode it clamps to the available height (as many lines as fit);
 * otherwise it clamps to a fixed line count. Renders the text and (conditionally) the toggle as
 * siblings so a parent flex column controls the spacing between them.
 */
export const ExpandableText: FC<ExpandableTextProps> = ({ text, lines = 3, fill = false }) => {
  const [expanded, setExpanded] = useState(false);
  const [isOverflowing, setIsOverflowing] = useState(false);
  // Measures the clamped element — the text span in fixed mode, the clipping box in fill mode.
  const measureRef = useRef<HTMLElement | null>(null);
  const setMeasureRef = (el: HTMLElement | null) => {
    measureRef.current = el;
  };

  // Only measure while clamped; when expanded the element is unclamped so we retain the last reading
  // and keep the toggle visible. A ResizeObserver re-measures when the available height changes.
  useLayoutEffect(() => {
    const el = measureRef.current;
    if (!el || expanded) return;
    const measure = () => setIsOverflowing(el.scrollHeight > el.clientHeight + 1);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [text, expanded, fill]);

  const toggle = isOverflowing ? (
    <button
      type="button"
      onClick={() => setExpanded((prev) => !prev)}
      className="w-fit cursor-pointer"
    >
      <Text kind="body/semibold/md" color="brand">
        {expanded ? '- View less' : '+ View more'}
      </Text>
    </button>
  ) : null;

  if (fill) {
    return (
      <Stack className="min-h-0 flex-1 gap-density-md">
        <div ref={setMeasureRef} className={expanded ? '' : 'min-h-0 flex-1 overflow-hidden'}>
          <Text kind="body/regular/md" className="whitespace-pre-wrap">
            {text}
          </Text>
        </div>
        {toggle}
      </Stack>
    );
  }

  return (
    <>
      <Text
        ref={setMeasureRef}
        kind="body/regular/md"
        className={expanded ? 'whitespace-pre-wrap' : CLAMP_CLASS[lines]}
      >
        {text}
      </Text>
      {toggle}
    </>
  );
};
