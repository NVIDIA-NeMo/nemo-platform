// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { AssistantChatRuntime } from '@studio/routes/agents/AssistantChatRoute/useAssistantChatRuntime';
import { createContext, useContext } from 'react';

export type AssistantChatLoadStatus = 'idle' | 'loading' | 'error';

export interface AssistantChatContextValue {
  /** The single chat runtime shared by the full chat route and the pop-out. */
  chat: AssistantChatRuntime;
  /** Status of the most recent `loadSession` fetch. */
  loadStatus: AssistantChatLoadStatus;
  /** Fetch a session's history and load it into the shared runtime. */
  loadSession: (sessionId: string) => void;
  /** Reset the shared runtime to a fresh, empty chat. */
  startNewChat: () => void;
}

export const AssistantChatContext = createContext<AssistantChatContextValue | null>(null);

export const useAssistantChatContext = (): AssistantChatContextValue => {
  const context = useContext(AssistantChatContext);
  if (!context) {
    throw new Error('useAssistantChatContext must be used within a AssistantChatProvider');
  }
  return context;
};
