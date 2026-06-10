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

export interface ClaudeCodeHistorySession {
  session_id: string;
  mtime: number;
  first_prompt: string;
  message_count: number;
  token_count: number;
  tool_call_count: number;
  tool_calls: string[];
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
}
