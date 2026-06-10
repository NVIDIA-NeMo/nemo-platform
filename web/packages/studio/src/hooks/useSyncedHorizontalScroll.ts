// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useCallback, useMemo, useRef } from 'react';

type ScrollCallbackRef = (el: HTMLElement | null) => void;

/**
 * Returns `count` stable callback refs whose elements share a single horizontal
 * scroll position. Scrolling any registered container mirrors its `scrollLeft`
 * onto the others, so rows with matching content widths (e.g. the Playground
 * chat panels and the performance-summary boxes below them) scroll as one.
 *
 * Containers may mount and unmount independently — a freshly mounted container
 * snaps to the group's current position, and unmounted ones detach cleanly.
 */
export function useSyncedHorizontalScroll(count: number): ScrollCallbackRef[] {
  const elements = useRef<Set<HTMLElement>>(new Set());
  // Guards against the programmatic scroll updates echoing back as new events.
  const isSyncing = useRef(false);

  const handleScroll = useCallback((event: Event) => {
    if (isSyncing.current) return;
    const source = event.currentTarget as HTMLElement;
    isSyncing.current = true;
    elements.current.forEach((el) => {
      if (el !== source && el.scrollLeft !== source.scrollLeft) {
        el.scrollLeft = source.scrollLeft;
      }
    });
    // Release on the next frame so the mirrored scrolls settle without looping.
    requestAnimationFrame(() => {
      isSyncing.current = false;
    });
  }, []);

  // One stable callback ref per slot. Each remembers the element it manages so
  // it can detach when React calls it with null on unmount.
  const slots = useRef<{ el: HTMLElement | null }[]>([]);

  return useMemo(
    () =>
      Array.from({ length: count }, (_, i) => {
        slots.current[i] ??= { el: null };
        const slot = slots.current[i];
        const ref: ScrollCallbackRef = (el) => {
          if (slot.el) {
            slot.el.removeEventListener('scroll', handleScroll);
            elements.current.delete(slot.el);
          }
          slot.el = el;
          if (el) {
            elements.current.add(el);
            el.addEventListener('scroll', handleScroll, { passive: true });
            const peer = [...elements.current].find((other) => other !== el);
            if (peer && el.scrollLeft !== peer.scrollLeft) {
              el.scrollLeft = peer.scrollLeft;
            }
          }
        };
        return ref;
      }),
    [count, handleScroll]
  );
}
