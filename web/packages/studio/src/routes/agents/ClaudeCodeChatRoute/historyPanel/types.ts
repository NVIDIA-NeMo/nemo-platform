// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ClaudeCodeChatArtifacts } from '@studio/routes/agents/ClaudeCodeChatRoute/types';

export interface ClaudeCodeHistoryPanelProps {
  activeSessionId?: string;
  artifacts?: ClaudeCodeChatArtifacts;
  hideArtifacts?: boolean;
  onNewChat: () => void;
  onSelectSession: (sessionId: string) => void;
}

export type ClaudeCodePanelTab = 'history' | 'skills';
