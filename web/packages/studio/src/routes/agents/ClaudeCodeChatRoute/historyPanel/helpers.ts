// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ClaudeCodePanelTab } from '@studio/routes/agents/ClaudeCodeChatRoute/historyPanel/types';
import type {
  ClaudeCodeChatArtifacts,
  ClaudeCodeChatFileArtifact,
} from '@studio/routes/agents/ClaudeCodeChatRoute/types';

export const isClaudeCodePanelTab = (value: string): value is ClaudeCodePanelTab =>
  value === 'history' || value === 'skills';

export const getCompactRelativeTime = (mtime: number): string => {
  const elapsedMs = Math.max(Date.now() - mtime * 1000, 0);
  const minuteMs = 60 * 1000;
  const hourMs = 60 * minuteMs;
  const dayMs = 24 * hourMs;

  if (elapsedMs < minuteMs) return 'now';
  if (elapsedMs < hourMs) return `${Math.floor(elapsedMs / minuteMs)}m`;
  if (elapsedMs < dayMs) return `${Math.floor(elapsedMs / hourMs)}h`;

  const days = Math.floor(elapsedMs / dayMs);
  if (days < 31) return `${days}d`;

  return new Date(mtime * 1000).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
  });
};

export const getFileLabel = (file: ClaudeCodeChatFileArtifact): string => {
  const parts = file.path.split('/');
  return parts[parts.length - 1] || file.path;
};

export const getSelectedArtifactModel = (artifacts: ClaudeCodeChatArtifacts): string | undefined =>
  artifacts.model_source === 'selection' || artifacts.model_source === 'spec'
    ? artifacts.model
    : undefined;

export const hasArtifacts = (
  artifacts?: ClaudeCodeChatArtifacts
): artifacts is ClaudeCodeChatArtifacts =>
  !!artifacts &&
  !!(
    artifacts.agent ||
    getSelectedArtifactModel(artifacts) ||
    artifacts.workspace ||
    artifacts.selections.length ||
    artifacts.files.length ||
    artifacts.links.length ||
    artifacts.jobs.length ||
    artifacts.tools.length
  );
