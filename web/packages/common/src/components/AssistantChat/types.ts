// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ThreadMessageLike } from '@assistant-ui/react';
import type { AssistantChatTool } from '@nemo/common/src/components/AssistantChat/tools/types';
import type { PromptData } from '@nemo/sdk/generated/platform/schema';

export interface AssistantChatProps {
  /**
   * The model name to route through inference gateway.
   */
  model: string;
  /**
   * Workspace used to build the default inference gateway URL.
   */
  workspace?: string;
  /**
   * Explicit OpenAI-compatible chat completions base URL. When omitted, `useChatCompletion`
   * resolves inference gateway routing from workspace and model.
   */
  baseURL?: string;
  /**
   * Optional prompt data used for system prompt and inference parameter defaults.
   */
  promptData?: PromptData;
  /**
   * Optional tools for the request. OpenAI-compatible tool definitions are forwarded
   * verbatim. Studio tools are executable client-side tools that are shown in the
   * composer tool menu and executed when enabled.
   */
  tools?: readonly AssistantChatTool[];
  /**
   * Tool names enabled by default when the thread mounts. Users can flip the rest via the
   * composer options menu. Defaults to none enabled.
   */
  defaultEnabledTools?: readonly string[];
  assistantName?: string;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  initialMessages?: readonly ThreadMessageLike[];
  onError?: (error: Error) => void;
  emptyState?: {
    slotHeading?: string;
    slotSubheading?: string;
  };
}
