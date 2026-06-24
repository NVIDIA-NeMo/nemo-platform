// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ClaudeCodePanelTab } from '@studio/routes/agents/ClaudeCodeChatRoute/historyPanel/types';
import type {
  ClaudeCodeChatArtifacts,
  ClaudeCodeChatFileArtifact,
  ClaudeCodeHistorySession,
} from '@studio/routes/agents/ClaudeCodeChatRoute/types';

const MAX_HISTORY_TITLE_WORDS = 8;
const MAX_HISTORY_TITLE_CHARS = 72;

const ACTIONABLE_OPENERS = [
  /^(?:please\s+)?(?:can|could|would|will|should)\s+(?:you|we)\b/i,
  /^is\s+it\s+possible\b/i,
  /^(?:i|we)\s+(?:need|want)\s+to\b/i,
  /^i(?:'d| would)\s+like(?:\s+you)?\s+to\b/i,
  /^help(?:\s+(?:me|us))?\b/i,
  /^let'?s\b/i,
];

const REQUEST_PREFIXES = [
  /^(?:please\s+)?(?:can|could|would|will|should)\s+(?:you|we)\s+/i,
  /^is\s+it\s+possible(?:\s+for\s+(?:us|you|me))?\s+to\s+/i,
  /^(?:i|we)\s+(?:need|want)\s+to\s+/i,
  /^i(?:'d| would)\s+like(?:\s+you)?\s+to\s+/i,
  /^help(?:\s+(?:me|us))?(?:\s+to)?\s+/i,
  /^let'?s\s+/i,
];

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

const getCleanTitleText = (value: string): string =>
  value
    .replace(/\([^()]*\)/g, ' ')
    .replace(/[`*_#>]+/g, '')
    .replace(/\s+/g, ' ')
    .trim();

const splitPromptSentences = (prompt: string): string[] =>
  (prompt.match(/[^.!?]+[.!?]*/g) ?? [prompt])
    .map((sentence) =>
      getCleanTitleText(sentence)
        .replace(/[.!?]+$/g, '')
        .trim()
    )
    .filter(Boolean);

const isActionableSentence = (sentence: string): boolean =>
  ACTIONABLE_OPENERS.some((pattern) => pattern.test(sentence));

const getPromptTitleSource = (prompt: string): string => {
  const sentences = splitPromptSentences(prompt);

  for (let index = sentences.length - 1; index >= 0; index -= 1) {
    if (isActionableSentence(sentences[index])) return sentences[index];
  }

  return sentences[0] ?? getCleanTitleText(prompt);
};

const stripRequestPrefix = (text: string): string => {
  let title = text;

  for (const pattern of REQUEST_PREFIXES) {
    title = title.replace(pattern, '');
  }

  return title.replace(/^please\s+/i, '').replace(/^give\s+(?:it|them|this|that)\s+/i, 'give ');
};

const capitalizeTitle = (title: string): string =>
  title ? `${title.charAt(0).toLocaleUpperCase()}${title.slice(1)}` : title;

const limitTitleLength = (title: string): string => {
  const words = title.split(/\s+/).filter(Boolean);
  let limited = words.slice(0, MAX_HISTORY_TITLE_WORDS).join(' ');

  if (limited.length > MAX_HISTORY_TITLE_CHARS) {
    limited = `${limited.slice(0, MAX_HISTORY_TITLE_CHARS - 3).trimEnd()}...`;
  }

  return limited;
};

const getPromptHistoryTitle = (prompt: string): string | undefined => {
  const source = getPromptTitleSource(prompt);
  const title = capitalizeTitle(
    stripRequestPrefix(source)
      .replace(/[,:;\s-]+$/g, '')
      .trim()
  );
  return title ? limitTitleLength(title) : undefined;
};

const getArtifactHistoryTitle = (artifacts: ClaudeCodeChatArtifacts): string | undefined => {
  if (artifacts.agent) return `Agent ${getCleanTitleText(artifacts.agent)}`;
  if (artifacts.jobs.length) return `Job ${getCleanTitleText(artifacts.jobs[0].name)}`;
  if (artifacts.files.length) {
    const file = artifacts.files[0];
    return `${getCleanTitleText(file.action)} ${getFileLabel(file)}`;
  }
  return undefined;
};

export const getHistorySessionTitle = (session: ClaudeCodeHistorySession): string =>
  getPromptHistoryTitle(session.first_prompt) ??
  getArtifactHistoryTitle(session.chat_artifacts) ??
  'Claude Code session';

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
