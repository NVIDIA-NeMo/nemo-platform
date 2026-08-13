// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { AssistantChatArtifacts } from '@studio/routes/agents/AssistantChatRoute/types';

export interface AssistantHistoryPanelProps {
  activeSessionId?: string;
  artifacts?: AssistantChatArtifacts;
  hideArtifacts?: boolean;
  onNewChat: () => void;
  onSelectSession: (sessionId: string) => void;
  workspace?: string;
}
