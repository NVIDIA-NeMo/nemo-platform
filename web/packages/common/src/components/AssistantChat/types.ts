// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ThreadMessageLike } from '@assistant-ui/react';
import type { PromptData } from '@nemo/sdk/generated/platform/schema';
import type { ChatCompletionTool } from 'openai/resources/index.mjs';
import type { ReactNode } from 'react';

import type { AssistantChatThreadAttributes } from './AssistantChatThread';

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
   * Optional OpenAI-compatible tools for the request.
   */
  tools?: ChatCompletionTool[];
  /**
   * Display name used in the composer placeholder.
   */
  assistantName?: string;
  placeholder?: string;
  disabled?: boolean;
  showRunningIndicator?: boolean;
  attributes?: AssistantChatThreadAttributes;
  className?: string;
  initialMessages?: readonly ThreadMessageLike[];
  onError?: (error: Error) => void;
  emptyState?: {
    slotHeading?: string;
    slotSubheading?: string;
  };
  composerOverride?: ReactNode;
}
