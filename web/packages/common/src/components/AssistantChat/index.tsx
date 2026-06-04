// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { AssistantRuntimeProvider } from '@assistant-ui/react';
import cn from 'classnames';
import { type FC, useMemo } from 'react';

import { AssistantChatThread } from './AssistantChatThread';
import type { AssistantChatProps } from './types';
import { useAssistantChatRuntime } from './useAssistantChatRuntime';

export type { AssistantChatProps } from './types';

export const AssistantChat: FC<AssistantChatProps> = ({
  model,
  workspace,
  baseURL,
  promptData,
  tools,
  assistantName,
  placeholder,
  disabled = false,
  showRunningIndicator,
  attributes,
  className,
  initialMessages = [],
  onError,
  emptyState,
  composerOverride,
}) => {
  const { handleReset, runtime } = useAssistantChatRuntime({
    model,
    workspace,
    baseURL,
    promptData,
    tools,
    disabled,
    initialMessages,
    onError,
  });

  const composerPlaceholder = useMemo(
    () => placeholder || `Message ${assistantName || model || 'Your Assistant'}`,
    [assistantName, model, placeholder]
  );

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <div className={cn('h-full w-full', className)}>
        <AssistantChatThread
          disabled={disabled}
          placeholder={composerPlaceholder}
          onReset={handleReset}
          showRunningIndicator={showRunningIndicator}
          attributes={attributes}
          emptyState={emptyState}
          composerOverride={composerOverride}
        />
      </div>
    </AssistantRuntimeProvider>
  );
};
