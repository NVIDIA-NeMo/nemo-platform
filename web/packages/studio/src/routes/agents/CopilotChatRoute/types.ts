// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

export interface CopilotStreamHandlers {
  onCopilotEvent: (event: unknown) => void;
  onInputRequest: (request: CopilotInputRequest) => void;
  onPermissionRequest: (request: CopilotPermissionRequest) => void;
  onInputExpired?: (requestId: string) => void;
  onPermissionExpired?: (requestId: string) => void;
  onDone: () => void;
  onError: (error: Error) => void;
}

export interface CopilotPermissionRequest {
  requestId: string;
  toolName: string;
  input: Record<string, unknown>;
  toolUseId?: string;
}

export interface CopilotPermissionDecision {
  approved: boolean;
  reason?: string;
  updatedInput?: Record<string, unknown>;
}

export type CopilotInputRequestKind = 'agent' | 'eval_config' | 'dataset_file' | 'model';

export interface CopilotInputRequest {
  requestId: string;
  kind: CopilotInputRequestKind;
  input: Record<string, unknown>;
}

export interface CopilotInputDecision {
  skipped?: boolean;
  value?: Record<string, unknown>;
}

export interface CopilotChatRouteState {
  initialPrompt?: string;
}

export interface CopilotChatSelectionArtifact {
  label: string;
  value: string;
}

export interface CopilotChatFileArtifact {
  action: string;
  path: string;
}

export interface CopilotChatLinkArtifact {
  label: string;
  destination?: string;
  href?: string;
}

export interface CopilotChatJobArtifact {
  name: string;
  job_type?: string;
  source?: string;
  href?: string;
}

export type CopilotChatModelSource = 'copilot' | 'selection' | 'spec';

export interface CopilotChatArtifacts {
  agent?: string;
  model?: string;
  model_source?: CopilotChatModelSource;
  copilot_model?: string;
  workspace?: string;
  selections: CopilotChatSelectionArtifact[];
  files: CopilotChatFileArtifact[];
  links: CopilotChatLinkArtifact[];
  jobs: CopilotChatJobArtifact[];
  tools: string[];
}

export interface CopilotHistorySession {
  session_id: string;
  mtime: number;
  title?: string;
  first_prompt: string;
  message_count: number;
  token_count: number;
  tool_call_count: number;
  tool_calls: string[];
  chat_artifacts: CopilotChatArtifacts;
}

export interface CopilotSkill {
  name: string;
  claude_name: string;
  description: string;
  source: string;
  source_path?: string | null;
  install_path: string;
  installed: boolean;
}

export interface CopilotUserHistoryItem {
  kind: 'user';
  text: string;
}

export interface CopilotAssistantTextPart {
  type: 'text';
  text: string;
}

export interface CopilotAssistantToolUsePart {
  type: 'tool_use';
  id?: string;
  name: string;
  input: Record<string, unknown>;
}

export type CopilotAssistantHistoryPart = CopilotAssistantTextPart | CopilotAssistantToolUsePart;

export interface CopilotAssistantHistoryItem {
  kind: 'assistant';
  parts: CopilotAssistantHistoryPart[];
}

export type CopilotSessionHistoryItem = CopilotUserHistoryItem | CopilotAssistantHistoryItem;

export interface CopilotSessionHistory {
  session_id: string;
  items: CopilotSessionHistoryItem[];
  chat_artifacts: CopilotChatArtifacts;
}
