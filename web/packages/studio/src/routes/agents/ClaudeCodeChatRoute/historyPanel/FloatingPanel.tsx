// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Text } from '@nvidia/foundations-react-core';
import { ChevronDown } from 'lucide-react';
import { type ReactNode } from 'react';

interface FloatingPanelProps {
  children: ReactNode;
  onOpenChange: (open: boolean) => void;
  open: boolean;
  title: string;
}

export const FloatingPanel = ({ children, onOpenChange, open, title }: FloatingPanelProps) => {
  const actionLabel = `${open ? 'Collapse' : 'Expand'} ${title}`;

  return (
    <section className="shrink-0 overflow-hidden rounded border border-base bg-surface-base dark:bg-surface-raised">
      <button
        aria-expanded={open}
        aria-label={actionLabel}
        className="flex w-full cursor-pointer items-center justify-between gap-density-sm px-density-md py-density-sm text-left text-secondary transition-colors hover:bg-surface-sunken focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
        type="button"
        onClick={() => onOpenChange(!open)}
      >
        <Text kind="label/bold/md">{title}</Text>
        <ChevronDown
          aria-hidden="true"
          className={`size-4 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`}
        />
      </button>
      {open && (
        <div className="flex max-h-96 min-h-0 flex-col border-t border-base">{children}</div>
      )}
    </section>
  );
};
