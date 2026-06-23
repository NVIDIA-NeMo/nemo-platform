// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ActionBarPrimitive, MessagePrimitive } from '@assistant-ui/react';
import { Tooltip } from '@nvidia/foundations-react-core';
import { Check, Copy } from 'lucide-react';

export const ACTION_BUTTON_CLASS =
  'flex cursor-pointer size-8 items-center justify-center rounded text-base bg-surface-raised hover:bg-surface-sunken disabled:cursor-not-allowed disabled:opacity-50';

export const MESSAGE_ACTIONS_CLASS =
  'flex gap-density-xs opacity-0 transition-opacity group-hover/message:opacity-100 group-focus-within/message:opacity-100 [@media(hover:none)]:opacity-100';

export const CopyAction = () => (
  <Tooltip slotContent="Copy message">
    <ActionBarPrimitive.Copy aria-label="Copy message" className={ACTION_BUTTON_CLASS}>
      <MessagePrimitive.If copied>
        <Check size={16} />
      </MessagePrimitive.If>
      <MessagePrimitive.If copied={false}>
        <Copy size={16} />
      </MessagePrimitive.If>
    </ActionBarPrimitive.Copy>
  </Tooltip>
);
