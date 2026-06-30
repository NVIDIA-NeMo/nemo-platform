// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

export interface ClaudeCodeStreamHandlers {
  onClaudeEvent: (event: unknown) => void;
  onInputRequest: (request: ClaudeCodeInputRequest) => void;
  onPermissionRequest: (request: ClaudeCodePermissionRequest) => void;
  onDone: () => void;
  onError: (error: Error) => void;
}

export interface ClaudeCodePermissionRequest {
  requestId: string;
  toolName: string;
  input: Record<string, unknown>;
  toolUseId?: string;
}

export interface ClaudeCodePermissionDecision {
  approved: boolean;
  reason?: string;
  updatedInput?: Record<string, unknown>;
}

export type ClaudeCodeInputRequestKind = 'agent' | 'eval_config' | 'dataset_file' | 'model';

export interface ClaudeCodeInputRequest {
  requestId: string;
  kind: ClaudeCodeInputRequestKind;
  input: Record<string, unknown>;
}

export interface ClaudeCodeInputDecision {
  skipped?: boolean;
  value?: Record<string, unknown>;
}

export interface ClaudeCodeChatRouteState {
  initialPrompt?: string;
}

export interface ClaudeCodeChatSelectionArtifact {
  label: string;
  value: string;
}

export interface ClaudeCodeChatFileArtifact {
  action: string;
  path: string;
}

export interface ClaudeCodeChatLinkArtifact {
  label: string;
  destination?: string;
  href?: string;
}

export interface ClaudeCodeChatJobArtifact {
  name: string;
  job_type?: string;
  source?: string;
  href?: string;
}

export type ClaudeCodeChatModelSource = 'coding_agent' | 'selection' | 'spec';

export interface ClaudeCodeChatArtifacts {
  agent?: string;
  model?: string;
  model_source?: ClaudeCodeChatModelSource;
  coding_agent_model?: string;
  workspace?: string;
  selections: ClaudeCodeChatSelectionArtifact[];
  files: ClaudeCodeChatFileArtifact[];
  links: ClaudeCodeChatLinkArtifact[];
  jobs: ClaudeCodeChatJobArtifact[];
  tools: string[];
}

export interface ClaudeCodeHistorySession {
  session_id: string;
  mtime: number;
  first_prompt: string;
  message_count: number;
  token_count: number;
  tool_call_count: number;
  tool_calls: string[];
  chat_artifacts: ClaudeCodeChatArtifacts;
}

export interface ClaudeCodeSkill {
  name: string;
  claude_name: string;
  description: string;
  source: string;
  source_path?: string | null;
  install_path: string;
  installed: boolean;
}

export interface ClaudeCodeUserHistoryItem {
  kind: 'user';
  text: string;
}

export interface ClaudeCodeAssistantTextPart {
  type: 'text';
  text: string;
}

export interface ClaudeCodeAssistantToolUsePart {
  type: 'tool_use';
  id?: string;
  name: string;
  input: Record<string, unknown>;
}

export type ClaudeCodeAssistantHistoryPart =
  | ClaudeCodeAssistantTextPart
  | ClaudeCodeAssistantToolUsePart;

export interface ClaudeCodeAssistantHistoryItem {
  kind: 'assistant';
  parts: ClaudeCodeAssistantHistoryPart[];
}

export type ClaudeCodeSessionHistoryItem =
  | ClaudeCodeUserHistoryItem
  | ClaudeCodeAssistantHistoryItem;

export interface ClaudeCodeSessionHistory {
  session_id: string;
  items: ClaudeCodeSessionHistoryItem[];
  chat_artifacts: ClaudeCodeChatArtifacts;
}
