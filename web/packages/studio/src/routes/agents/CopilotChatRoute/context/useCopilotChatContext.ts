// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { CopilotChatRuntime } from '@studio/routes/agents/CopilotChatRoute/useCopilotChatRuntime';
import { createContext, useContext } from 'react';

export type CopilotChatLoadStatus = 'idle' | 'loading' | 'error';

export interface CopilotChatContextValue {
  /** The single chat runtime shared by the full chat route and the pop-out. */
  chat: CopilotChatRuntime;
  /** Status of the most recent `loadSession` fetch. */
  loadStatus: CopilotChatLoadStatus;
  /** Fetch a session's history and load it into the shared runtime. */
  loadSession: (sessionId: string) => void;
  /** Reset the shared runtime to a fresh, empty chat. */
  startNewChat: () => void;
}

export const CopilotChatContext = createContext<CopilotChatContextValue | null>(null);

export const useCopilotChatContext = (): CopilotChatContextValue => {
  const context = useContext(CopilotChatContext);
  if (!context) {
    throw new Error('useCopilotChatContext must be used within a CopilotChatProvider');
  }
  return context;
};
