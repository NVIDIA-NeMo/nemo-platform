// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ReasoningMessagePartComponent } from '@assistant-ui/react';
import { MessageContent } from '@nemo/common/src/components/Chat/MessageContent';
import { Text } from '@nvidia/foundations-react-core';
import { ChevronRight } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

export const ClaudeCodeReasoningPart: ReasoningMessagePartComponent = ({ status, text }) => {
  const isRunning = status.type === 'running';
  const [isOpen, setIsOpen] = useState(isRunning);
  const wasRunningRef = useRef(isRunning);

  useEffect(() => {
    if (wasRunningRef.current && !isRunning) {
      setIsOpen(false);
    }
    wasRunningRef.current = isRunning;
  }, [isRunning]);

  return (
    <details
      className="group/think my-density-sm rounded border border-base bg-surface-raised"
      data-testid="claude-code-thinking-block"
      open={isOpen}
      onToggle={(event) => setIsOpen(event.currentTarget.open)}
    >
      <summary className="flex cursor-pointer list-none items-center gap-density-xs px-density-sm py-density-xs text-secondary marker:hidden">
        <ChevronRight
          size={14}
          className="shrink-0 transition-transform group-open/think:rotate-90"
        />
        <Text kind="label/bold/sm">Thinking</Text>
      </summary>
      <div className="border-t border-base px-density-md py-density-sm text-secondary">
        <MessageContent content={text} />
      </div>
    </details>
  );
};
