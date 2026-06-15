// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import cn from 'classnames';
import { GripVertical } from 'lucide-react';
import { type FC, type ReactNode, useCallback, useEffect, useRef, useState } from 'react';

interface ResizeablePanelProps {
  slotLeft: ReactNode;
  slotRight: ReactNode;
  defaultLeftWidth?: number;
  minLeftWidth?: number;
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
  maxLeftWidth,
  leftClassName,
  rightClassName,
  className,
}) => {
  const [leftWidth, setLeftWidth] = useState(defaultLeftWidth);
  const [isDragging, setIsDragging] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      setIsDragging(true);

      const handleMouseMove = (ev: MouseEvent) => {
        if (!containerRef.current) return;
        const rect = containerRef.current.getBoundingClientRect();
        const max = maxLeftWidth ?? rect.width - minLeftWidth;
        const next = Math.max(minLeftWidth, Math.min(max, ev.clientX - rect.left));
        setLeftWidth(next);
      };

      const handleMouseUp = () => {
        setIsDragging(false);
        window.removeEventListener('mousemove', handleMouseMove);
        window.removeEventListener('mouseup', handleMouseUp);
      };

      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
    },
    [minLeftWidth, maxLeftWidth]
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

  return (
    <div ref={containerRef} className={cn('flex h-full w-full', className)}>
      {/* Left panel */}
      <div
        // eslint-disable-next-line no-restricted-syntax
        style={{ width: leftWidth }}
        className={cn(
          'shrink-0 overflow-y-auto rounded-bl-xl rounded-tl-xl border border-base bg-surface-raised',
          leftClassName
        )}
      >
        {slotLeft}
      </div>

      {/* Drag handle */}
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize panels"
        className={cn(
          'group relative flex w-3 shrink-0 cursor-col-resize items-center justify-center border-y border-base bg-surface-raised',
          isDragging && 'bg-surface-hover'
        )}
        onMouseDown={handleMouseDown}
      >
        {/* Vertical line */}
        <div
          className={cn(
            'absolute inset-y-0 left-[5px] w-px bg-border-base transition-colors',
            'group-hover:bg-border-strong',
            isDragging && 'bg-border-brand'
          )}
        />
        {/* Grip icon */}
        <GripVertical
          className={cn(
            'relative z-10 size-3 text-content-secondary transition-opacity',
            'opacity-0 group-hover:opacity-100',
            isDragging && 'opacity-100 text-content-brand'
          )}
          aria-hidden
        />
      </div>

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
