// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Stack } from '@nvidia/foundations-react-core';
import { GripVertical } from 'lucide-react';
import {
  type FC,
  type KeyboardEvent,
  type MouseEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react';

const SIDEBAR_MIN_WIDTH_PX = 18 * 16;
const DETAIL_MIN_WIDTH_PX = 20 * 16;
const RESIZE_STEP_PX = 16;

interface TraceDetailLayoutProps {
  navigation: ReactNode;
  children: ReactNode;
}

/** Shared two-pane shell for Session, trace, and span detail selections. */
export const TraceDetailLayout: FC<TraceDetailLayoutProps> = ({ navigation, children }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [sidebarWidth, setSidebarWidth] = useState(SIDEBAR_MIN_WIDTH_PX);
  const [sidebarMaxWidth, setSidebarMaxWidth] = useState(SIDEBAR_MIN_WIDTH_PX);
  const [isResizing, setIsResizing] = useState(false);

  const measureSidebarMaxWidth = useCallback((): number => {
    const container = containerRef.current;
    const containerWidth = container?.getBoundingClientRect().width ?? 0;
    const columnGap = container ? Number.parseFloat(getComputedStyle(container).columnGap) || 0 : 0;
    return Math.max(SIDEBAR_MIN_WIDTH_PX, containerWidth - DETAIL_MIN_WIDTH_PX - columnGap);
  }, []);

  useEffect(() => {
    const updateSidebarBounds = () => {
      const maxWidth = measureSidebarMaxWidth();
      setSidebarMaxWidth(maxWidth);
      setSidebarWidth((width) => Math.min(width, maxWidth));
    };

    updateSidebarBounds();

    if (!containerRef.current || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(updateSidebarBounds);
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, [measureSidebarMaxWidth]);

  useEffect(() => {
    if (!isResizing) return;

    const handleMouseMove = (event: globalThis.MouseEvent) => {
      const containerLeft = containerRef.current?.getBoundingClientRect().left ?? 0;
      const maxWidth = measureSidebarMaxWidth();
      setSidebarMaxWidth(maxWidth);
      setSidebarWidth(
        Math.max(SIDEBAR_MIN_WIDTH_PX, Math.min(maxWidth, event.clientX - containerLeft))
      );
    };
    const handleMouseUp = () => setIsResizing(false);

    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);

    return () => {
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isResizing, measureSidebarMaxWidth]);

  const handleResizeStart = (event: MouseEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsResizing(true);
  };

  const handleResizeKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    let nextWidth: number | undefined;
    if (event.key === 'ArrowLeft') nextWidth = sidebarWidth - RESIZE_STEP_PX;
    if (event.key === 'ArrowRight') nextWidth = sidebarWidth + RESIZE_STEP_PX;
    if (event.key === 'Home') nextWidth = SIDEBAR_MIN_WIDTH_PX;
    if (event.key === 'End') nextWidth = sidebarMaxWidth;
    if (nextWidth === undefined) return;

    event.preventDefault();
    setSidebarWidth(Math.max(SIDEBAR_MIN_WIDTH_PX, Math.min(sidebarMaxWidth, nextWidth)));
  };

  return (
    <div ref={containerRef} className="flex min-w-0 items-start gap-density-md">
      <div
        data-testid="trace-trajectory-sidebar"
        // eslint-disable-next-line no-restricted-syntax
        style={{ width: sidebarWidth }}
        className="sticky top-density-lg hidden max-h-[calc(100vh-6rem)] shrink-0 self-start lg:block"
      >
        <aside className="max-h-[calc(100vh-6rem)] overflow-y-auto rounded-lg bg-surface-raised p-density-xs">
          {navigation}
        </aside>
        <div
          role="separator"
          aria-label="Resize trace trajectory sidebar"
          aria-orientation="vertical"
          aria-valuemin={SIDEBAR_MIN_WIDTH_PX}
          aria-valuemax={sidebarMaxWidth}
          aria-valuenow={sidebarWidth}
          tabIndex={0}
          className="group absolute inset-y-0 -right-[calc(var(--spacing-density-md)/2)] flex w-[var(--spacing-density-md)] cursor-col-resize items-center justify-center focus-visible:outline-none"
          onMouseDown={handleResizeStart}
          onKeyDown={handleResizeKeyDown}
        >
          <span
            className={`flex h-10 w-1 items-center justify-center rounded-full bg-border-base transition-colors group-hover:bg-border-strong group-focus-visible:bg-border-brand${
              isResizing ? ' bg-border-brand' : ''
            }`}
          >
            <GripVertical aria-hidden className="size-3 max-w-none text-secondary" />
          </span>
        </div>
      </div>
      <Stack gap="density-lg" className="min-w-0 flex-1">
        {children}
      </Stack>
    </div>
  );
};
