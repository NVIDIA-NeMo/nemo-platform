// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import cn from 'classnames';
import { GripVertical } from 'lucide-react';
import { type FC, type ReactNode, useCallback, useEffect, useRef, useState } from 'react';

const DIVIDER_WIDTH = 12;

interface ResizeablePanelProps {
  slotLeft: ReactNode;
  slotRight: ReactNode;
  defaultLeftWidth?: number;
  minLeftWidth?: number;
  minRightWidth?: number;
  maxLeftWidth?: number;
  leftClassName?: string;
  rightClassName?: string;
  className?: string;
}

export const ResizeablePanel: FC<ResizeablePanelProps> = ({
  slotLeft,
  slotRight,
  defaultLeftWidth = 410,
  minLeftWidth = 200,
  minRightWidth = minLeftWidth,
  maxLeftWidth,
  leftClassName,
  rightClassName,
  className,
}) => {
  const [leftWidth, setLeftWidth] = useState(defaultLeftWidth);
  const [isDragging, setIsDragging] = useState(false);
  const [isStacked, setIsStacked] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const resolvedMaxWidth = useCallback(() => {
    const containerWidth = containerRef.current?.getBoundingClientRect().width ?? 0;
    if (containerWidth <= 0) return maxLeftWidth ?? Number.MAX_SAFE_INTEGER;
    const availableWidth = containerWidth - minRightWidth - DIVIDER_WIDTH;
    return maxLeftWidth === undefined ? availableWidth : Math.min(maxLeftWidth, availableWidth);
  }, [maxLeftWidth, minRightWidth]);

  const clampWidth = useCallback(
    (width: number) => Math.max(minLeftWidth, Math.min(resolvedMaxWidth(), width)),
    [minLeftWidth, resolvedMaxWidth]
  );

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      setIsDragging(true);

      const handleMouseMove = (ev: MouseEvent) => {
        if (!containerRef.current) return;
        const rect = containerRef.current.getBoundingClientRect();
        setLeftWidth(clampWidth(ev.clientX - rect.left));
      };

      const handleMouseUp = () => {
        setIsDragging(false);
        window.removeEventListener('mousemove', handleMouseMove);
        window.removeEventListener('mouseup', handleMouseUp);
      };

      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
    },
    [clampWidth]
  );

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      const increment = event.shiftKey ? 48 : 24;
      if (event.key === 'ArrowLeft') setLeftWidth((width) => clampWidth(width - increment));
      else if (event.key === 'ArrowRight') setLeftWidth((width) => clampWidth(width + increment));
      else if (event.key === 'Home') setLeftWidth(minLeftWidth);
      else if (event.key === 'End') setLeftWidth(resolvedMaxWidth());
      else return;
      event.preventDefault();
    },
    [clampWidth, minLeftWidth, resolvedMaxWidth]
  );

  // Prevent text selection while dragging
  useEffect(() => {
    if (isDragging) {
      document.body.style.userSelect = 'none';
      document.body.style.cursor = 'col-resize';
    } else {
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
    }
    return () => {
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
    };
  }, [isDragging]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(([entry]) => {
      const stacked = entry.contentRect.width < minLeftWidth + minRightWidth + DIVIDER_WIDTH;
      setIsStacked(stacked);
      if (!stacked) setLeftWidth((width) => clampWidth(width));
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, [clampWidth, minLeftWidth, minRightWidth]);

  return (
    <div
      ref={containerRef}
      className={cn('flex w-full', isStacked ? 'flex-col' : 'h-full', className)}
    >
      {/* Left panel */}
      <div
        // eslint-disable-next-line no-restricted-syntax
        style={{ width: isStacked ? '100%' : leftWidth }}
        className={cn(
          'shrink-0 overflow-y-auto rounded-bl-xl rounded-tl-xl border border-base bg-surface-raised',
          leftClassName
        )}
      >
        {slotLeft}
      </div>

      {/* Drag handle */}
      {!isStacked ? (
        <div
          role="separator"
          tabIndex={0}
          aria-orientation="vertical"
          aria-label="Resize panels"
          aria-valuemin={minLeftWidth}
          aria-valuemax={Math.round(resolvedMaxWidth())}
          aria-valuenow={Math.round(leftWidth)}
          className={cn(
            'group relative flex w-3 shrink-0 cursor-col-resize items-center justify-center border-y border-base bg-surface-raised',
            isDragging && 'bg-surface-hover'
          )}
          onMouseDown={handleMouseDown}
          onKeyDown={handleKeyDown}
        >
          <div
            className={cn(
              'absolute inset-y-0 left-[5px] w-px bg-border-base transition-colors',
              'group-hover:bg-border-strong',
              isDragging && 'bg-border-brand'
            )}
          />
          <GripVertical
            className={cn(
              'relative z-10 size-3 text-content-secondary transition-opacity',
              'opacity-0 group-hover:opacity-100',
              isDragging && 'opacity-100 text-content-brand'
            )}
            aria-hidden
          />
        </div>
      ) : null}

      {/* Right panel */}
      <div
        className={cn(
          'flex-1 overflow-hidden rounded-br-xl rounded-tr-xl border border-base bg-surface-raised',
          rightClassName
        )}
      >
        {slotRight}
      </div>
    </div>
  );
};
