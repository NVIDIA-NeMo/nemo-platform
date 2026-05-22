// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Spinner, Text } from '@nvidia/foundations-react-core';
import cn from 'classnames';
import { AlertTriangle, Check, ChevronRight } from 'lucide-react';
import type { ReactNode } from 'react';

export interface ToolCallShellStatus {
  readonly type: 'running' | 'complete' | 'incomplete' | 'requires-action' | string;
  readonly reason?: string;
}

interface ToolCallShellProps {
  readonly icon: ReactNode;
  readonly label: string;
  readonly toolName: string;
  readonly status: ToolCallShellStatus;
  readonly summaryRight?: ReactNode;
  readonly children: ReactNode;
  readonly defaultOpen?: boolean;
}

const StatusPip = ({ status }: { status: ToolCallShellStatus }) => {
  if (status.type === 'running') {
    return <Spinner size="small" aria-label="Running" />;
  }
  if (status.type === 'incomplete') {
    return (
      <AlertTriangle
        size={14}
        aria-label={status.reason === 'cancelled' ? 'Cancelled' : 'Failed'}
        className="text-fg-status-warning"
      />
    );
  }
  return <Check size={14} aria-label="Complete" className="text-fg-status-positive" />;
};

export const ToolCallShell = ({
  icon,
  label,
  toolName,
  status,
  summaryRight,
  children,
  defaultOpen = false,
}: ToolCallShellProps) => (
  <details
    data-testid="assistant-chat-tool-call"
    data-tool-name={toolName}
    data-status={status.type}
    open={defaultOpen}
    className="group/tool-call my-density-sm overflow-hidden rounded-lg border border-base bg-surface-raised"
  >
    <summary
      className={cn(
        'flex cursor-pointer list-none items-center gap-density-xs px-density-sm py-density-xs text-sm',
        'hover:bg-surface-sunken'
      )}
    >
      <ChevronRight
        size={14}
        className="transition-transform group-open/tool-call:rotate-90"
        aria-hidden
      />
      <span className="flex size-5 items-center justify-center text-fg-muted">{icon}</span>
      <Text kind="label/regular/sm" className="truncate">
        {label}
      </Text>
      <span className="ml-auto flex min-w-0 items-center gap-density-xs">
        {summaryRight}
        <StatusPip status={status} />
      </span>
    </summary>
    <div className="border-t border-base bg-surface-base">{children}</div>
  </details>
);
