// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Button, Flex, Select, TextArea } from '@nvidia/foundations-react-core';
import type { GuardrailCheckMessage } from '@studio/api/guardrail-checks/types';
import { ChevronDown, ChevronUp, Copy, Sparkles, Trash2 } from 'lucide-react';
import type { FC } from 'react';

const ROLE_OPTIONS: Array<GuardrailCheckMessage['role']> = ['user', 'assistant', 'system'];

interface GuardrailMessageRowProps {
  message: GuardrailCheckMessage;
  isFirst: boolean;
  isLast: boolean;
  isGenerating?: boolean;
  onChange: (message: GuardrailCheckMessage) => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onCopy: () => void;
  onDelete: () => void;
  onGenerateResponse?: () => void;
  onBlur?: () => void;
}

export const GuardrailMessageRow: FC<GuardrailMessageRowProps> = ({
  message,
  isFirst,
  isLast,
  isGenerating,
  onChange,
  onMoveUp,
  onMoveDown,
  onCopy,
  onDelete,
  onGenerateResponse,
  onBlur,
}) => {
  const content = typeof message.content === 'string' ? message.content : '';

  return (
    <Flex gap="density-sm" align="start" className="w-full">
      <Select
        items={ROLE_OPTIONS}
        value={message.role}
        onValueChange={(role) =>
          // Cast is safe: role is always from ROLE_OPTIONS which are valid message roles
          onChange({ ...message, role } as GuardrailCheckMessage)
        }
        className="w-[120px] shrink-0"
        attributes={{ SelectTrigger: { 'aria-label': 'Message role' } }}
      />

      <TextArea
        value={content}
        onValueChange={(val) => onChange({ ...message, content: val })}
        onBlur={onBlur}
        rows={3}
        className="flex-1 min-w-0"
        attributes={{
          TextAreaElement: {
            'aria-label': `${message.role} message`,
            className: 'resize-y',
          },
        }}
      />

      <Flex direction="column" gap="density-xs" className="shrink-0 pt-1">
        <Button
          kind="tertiary"
          color="neutral"
          size="small"
          disabled={isFirst}
          onClick={onMoveUp}
          aria-label="Move message up"
        >
          <ChevronUp size={14} />
        </Button>
        <Button
          kind="tertiary"
          color="neutral"
          size="small"
          disabled={isLast}
          onClick={onMoveDown}
          aria-label="Move message down"
        >
          <ChevronDown size={14} />
        </Button>
        <Button
          kind="tertiary"
          color="neutral"
          size="small"
          onClick={onCopy}
          aria-label="Copy message"
        >
          <Copy size={14} />
        </Button>
        <Button
          kind="tertiary"
          color="danger"
          size="small"
          onClick={onDelete}
          aria-label="Delete message"
        >
          <Trash2 size={14} />
        </Button>
        {isLast && onGenerateResponse != null ? (
          <Button
            kind="tertiary"
            color="neutral"
            size="small"
            disabled={isGenerating}
            onClick={onGenerateResponse}
            aria-label="Generate response"
          >
            <Sparkles size={14} />
          </Button>
        ) : null}
      </Flex>
    </Flex>
  );
};
