// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { CopilotChatArtifacts } from '@studio/routes/agents/CopilotChatRoute/types';

export interface CopilotHistoryPanelProps {
  activeSessionId?: string;
  artifacts?: CopilotChatArtifacts;
  hideArtifacts?: boolean;
  onNewChat: () => void;
  onSelectSession: (sessionId: string) => void;
  workspace?: string;
}
