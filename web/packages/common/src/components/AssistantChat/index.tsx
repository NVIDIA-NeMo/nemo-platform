// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { AssistantRuntimeProvider } from '@assistant-ui/react';
import { AssistantChatThread } from '@nemo/common/src/components/AssistantChat/AssistantChatThread';
import { isStudioTool } from '@nemo/common/src/components/AssistantChat/tools';
import { useInstallPlatformWebSearchProvider } from '@nemo/common/src/components/AssistantChat/tools/usePlatformWebSearch';
import type { AssistantChatProps } from '@nemo/common/src/components/AssistantChat/types';
import { useAssistantChatRuntime } from '@nemo/common/src/components/AssistantChat/useAssistantChatRuntime';
import cn from 'classnames';
import { type FC, useCallback, useMemo, useState } from 'react';

export type { AssistantChatProps } from '@nemo/common/src/components/AssistantChat/types';
export {
  DEFAULT_STUDIO_TOOLS,
  getAssistantChatToolName,
  isStudioTool,
  setWebSearchProvider,
  type AssistantChatTool,
  type StudioTool,
  type StudioToolRegistry,
  type WebSearchProvider,
} from '@nemo/common/src/components/AssistantChat/tools';

export const AssistantChat: FC<AssistantChatProps> = ({
  model,
  workspace,
  baseURL,
  promptData,
  tools = [],
  defaultEnabledTools,
  assistantName,
  placeholder,
  disabled = false,
  className,
  initialMessages = [],
  onError,
  emptyState,
}) => {
  const [enabledToolNames, setEnabledToolNames] = useState<ReadonlySet<string>>(
    () => new Set(defaultEnabledTools ?? [])
  );

  const executableTools = useMemo(() => tools.filter(isStudioTool), [tools]);
  const hasWebSearchTool = useMemo(
    () => executableTools.some((tool) => tool.name === 'web_search'),
    [executableTools]
  );
  useInstallPlatformWebSearchProvider(hasWebSearchTool);

  const handleToggleTool = useCallback((toolName: string, enabled: boolean) => {
    setEnabledToolNames((prev) => {
      const next = new Set(prev);
      if (enabled) next.add(toolName);
      else next.delete(toolName);
      return next;
    });
  }, []);

  const { handleReset, runtime } = useAssistantChatRuntime({
    model,
    workspace,
    baseURL,
    promptData,
    tools,
    enabledStudioToolNames: enabledToolNames,
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
          emptyState={emptyState}
          tools={executableTools}
          enabledToolNames={enabledToolNames}
          onToggleTool={handleToggleTool}
        />
      </div>
    </AssistantRuntimeProvider>
  );
};
