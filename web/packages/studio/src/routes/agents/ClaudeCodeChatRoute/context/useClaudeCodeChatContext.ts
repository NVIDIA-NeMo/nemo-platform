// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ClaudeCodeChatRuntime } from '@studio/routes/agents/ClaudeCodeChatRoute/useClaudeCodeChatRuntime';
import { createContext, useContext } from 'react';

export type ClaudeCodeChatLoadStatus = 'idle' | 'loading' | 'error';

export interface ClaudeCodeChatContextValue {
  /** The single chat runtime shared by the full chat route and the pop-out. */
  chat: ClaudeCodeChatRuntime;
  /** Status of the most recent `loadSession` fetch. */
  loadStatus: ClaudeCodeChatLoadStatus;
  /** Fetch a session's history and load it into the shared runtime. */
  loadSession: (sessionId: string) => void;
  /** Reset the shared runtime to a fresh, empty chat. */
  startNewChat: () => void;
}

export const ClaudeCodeChatContext = createContext<ClaudeCodeChatContextValue | null>(null);

export const useClaudeCodeChatContext = (): ClaudeCodeChatContextValue => {
  const context = useContext(ClaudeCodeChatContext);
  if (!context) {
    throw new Error('useClaudeCodeChatContext must be used within a ClaudeCodeChatProvider');
  }
  return context;
};
