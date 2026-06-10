// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type {
  ClaudeCodeChatArtifacts,
  ClaudeCodeChatFileArtifact,
  ClaudeCodeChatLinkArtifact,
  ClaudeCodeChatSelectionArtifact,
  ClaudeCodeSessionHistoryItem,
} from '@studio/routes/agents/ClaudeCodeChatRoute/types';

interface ClaudeCodeArtifactQuestion {
  header?: string;
  question: string;
}

const FILE_CHANGE_TOOL_ACTIONS = new Map([
  ['Edit', 'Edited'],
  ['MultiEdit', 'Edited'],
  ['Write', 'Wrote'],
]);

const STUDIO_CONTEXT_WORKSPACE_RE = /^Current Studio workspace:\s*(?<workspace>.+)$/m;
const SPEC_HEADINGS = new Set([
  'behavior',
  'change scope',
  'evaluation setup',
  'framework',
  'harness',
  'model',
  'name',
  'open questions',
  'purpose',
  'role',
  'scope',
  'signals',
  'success criteria',
  'tools',
]);

export const createEmptyClaudeCodeChatArtifacts = (): ClaudeCodeChatArtifacts => ({
  selections: [],
  files: [],
  links: [],
  tools: [],
});

export const cleanClaudeCodeArtifactText = (value: string): string => {
  const trimmed = value.trim();
  const inlineCodeMatch = trimmed.match(/(`+)([\s\S]*?)\1/);
  if (!inlineCodeMatch) return trimmed;

  const unwrapped = inlineCodeMatch[2]?.trim();
  return unwrapped || trimmed;
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const getString = (value: unknown): string | undefined => {
  if (typeof value !== 'string') return undefined;
  const trimmed = value.trim();
  return trimmed || undefined;
};

const cloneArtifacts = (artifacts: ClaudeCodeChatArtifacts): ClaudeCodeChatArtifacts => ({
  agent: artifacts.agent,
  model: artifacts.model,
  model_source: artifacts.model_source,
  coding_agent_model: artifacts.coding_agent_model,
  workspace: artifacts.workspace,
  selections: [...artifacts.selections],
  files: [...artifacts.files],
  links: [...artifacts.links],
  tools: [...artifacts.tools],
});

const pushUnique = (items: string[], value: string) => {
  if (!items.includes(value)) items.push(value);
};

const inferSelectionLabel = (question: string, header?: string): string => {
  const combined = `${header ?? ''} ${question}`.toLowerCase();
  if (combined.includes('agent')) return 'Agent';
  if (combined.includes('model')) return 'Model';
  if (combined.includes('deployment')) return 'Deployment';
  if (combined.includes('fileset')) return 'Fileset';
  if (combined.includes('dataset')) return 'Dataset';
  if (combined.includes('provider')) return 'Provider';

  const label = header?.trim() || question.trim().replace(/\?$/, '');
  return label.length > 40 ? label.slice(0, 40) : label;
};

const setCodingAgentModel = (artifacts: ClaudeCodeChatArtifacts, model: string) => {
  artifacts.coding_agent_model = model;
};

const setSpecModel = (artifacts: ClaudeCodeChatArtifacts, model: string) => {
  artifacts.model = model;
  artifacts.model_source = 'spec';
};

const setSelection = (
  artifacts: ClaudeCodeChatArtifacts,
  selection: ClaudeCodeChatSelectionArtifact
) => {
  const cleanedSelection: ClaudeCodeChatSelectionArtifact = {
    ...selection,
    value: cleanClaudeCodeArtifactText(selection.value),
  };

  if (cleanedSelection.label === 'Agent') {
    artifacts.agent = cleanedSelection.value;
    return;
  }
  if (cleanedSelection.label === 'Model') {
    artifacts.model = cleanedSelection.value;
    artifacts.model_source = 'selection';
    return;
  }

  const existingIndex = artifacts.selections.findIndex(
    (item) => item.label === cleanedSelection.label
  );
  if (existingIndex >= 0) {
    artifacts.selections[existingIndex] = cleanedSelection;
    return;
  }
  artifacts.selections.push(cleanedSelection);
};

const upsertFile = (artifacts: ClaudeCodeChatArtifacts, file: ClaudeCodeChatFileArtifact) => {
  const existingIndex = artifacts.files.findIndex((item) => item.path === file.path);
  if (existingIndex >= 0) {
    artifacts.files[existingIndex] = file;
    return;
  }
  artifacts.files.push(file);
};

const appendLink = (artifacts: ClaudeCodeChatArtifacts, link: ClaudeCodeChatLinkArtifact) => {
  if (
    artifacts.links.some(
      (item) => item.label === link.label && item.destination === link.destination
    )
  ) {
    return;
  }
  artifacts.links.push(link);
};

const normalizeSpecLine = (line: string): string =>
  line
    .trim()
    .replace(/^#{1,6}\s+/, '')
    .replace(/^\s*[-*]\s+/, '')
    .replace(/\*\*/g, '')
    .trim();

const normalizeHeading = (line: string): string =>
  normalizeSpecLine(line).replace(/:$/, '').trim().toLowerCase();

const getInlineSpecValue = (text: string, label: string): string | undefined => {
  const prefix = `${label.toLowerCase()}:`;

  for (const line of text.split('\n')) {
    const normalized = normalizeSpecLine(line);
    if (!normalized.toLowerCase().startsWith(prefix)) continue;

    return getString(normalized.slice(prefix.length));
  }

  return undefined;
};

const cleanSpecValue = (value: string): string => {
  const normalized = normalizeSpecLine(value);
  const withoutParenthetical = normalized.replace(/\s+\([^)]*\)\s*$/, '').trim();
  return cleanClaudeCodeArtifactText(withoutParenthetical || normalized);
};

const getSectionSpecValue = (text: string, heading: string): string | undefined => {
  const lines = text.split('\n');
  const targetHeading = heading.toLowerCase();

  for (let index = 0; index < lines.length; index += 1) {
    if (normalizeHeading(lines[index] ?? '') !== targetHeading) continue;

    for (let valueIndex = index + 1; valueIndex < lines.length; valueIndex += 1) {
      const normalized = normalizeSpecLine(lines[valueIndex] ?? '');
      if (!normalized) continue;
      if (SPEC_HEADINGS.has(normalizeHeading(normalized))) return undefined;
      return cleanSpecValue(normalized);
    }
  }

  return undefined;
};

const recordSpecTextArtifacts = (artifacts: ClaudeCodeChatArtifacts, text: string) => {
  const agentName = getInlineSpecValue(text, 'Name') ?? getInlineSpecValue(text, 'Draft Spec');
  if (agentName) artifacts.agent = cleanSpecValue(agentName);

  const specModel = getSectionSpecValue(text, 'Model') ?? getInlineSpecValue(text, 'Model');
  if (specModel) setSpecModel(artifacts, cleanSpecValue(specModel));
};

const recordToolArtifacts = (
  artifacts: ClaudeCodeChatArtifacts,
  toolName: string,
  input: unknown
) => {
  pushUnique(artifacts.tools, toolName);

  const action = FILE_CHANGE_TOOL_ACTIONS.get(toolName);
  if (action && isRecord(input)) {
    const path = getString(input.file_path) ?? getString(input.path);
    if (path) upsertFile(artifacts, { action, path });
  }

  if ((toolName === 'studio_link' || toolName.endsWith('__studio_link')) && isRecord(input)) {
    const destination = getString(input.destination);
    const label = getString(input.label) ?? destination;
    if (label) appendLink(artifacts, { label, destination });
  }
};

export const updateClaudeCodeChatArtifactsFromEvent = (
  current: ClaudeCodeChatArtifacts,
  event: unknown
): ClaudeCodeChatArtifacts => {
  if (!isRecord(event)) return current;

  const next = cloneArtifacts(current);
  const message = isRecord(event.message) ? event.message : undefined;
  const model = getString(message?.model);
  if (model) setCodingAgentModel(next, model);

  const content = message?.content;
  if (!Array.isArray(content)) return next;

  for (const part of content) {
    if (!isRecord(part)) continue;

    if (part.type === 'text') {
      const text = getString(part.text);
      if (text) recordSpecTextArtifacts(next, text);
      continue;
    }

    if (part.type !== 'tool_use') continue;
    const toolName = getString(part.name) ?? 'tool';
    recordToolArtifacts(next, toolName, part.input);
  }

  return next;
};

export const updateClaudeCodeChatArtifactsFromSelections = (
  current: ClaudeCodeChatArtifacts,
  questions: readonly ClaudeCodeArtifactQuestion[],
  answers: Record<string, string>
): ClaudeCodeChatArtifacts => {
  const next = cloneArtifacts(current);

  for (const question of questions) {
    const answer = getString(answers[question.question]);
    if (!answer) continue;
    setSelection(next, {
      label: inferSelectionLabel(question.question, question.header),
      value: answer,
    });
  }

  return next;
};

export const updateClaudeCodeChatArtifactsFromUserText = (
  current: ClaudeCodeChatArtifacts,
  text: string
): ClaudeCodeChatArtifacts => {
  const next = cloneArtifacts(current);
  const workspace = text.match(STUDIO_CONTEXT_WORKSPACE_RE)?.groups?.workspace?.trim();
  if (workspace && !next.workspace) next.workspace = workspace;
  return next;
};

export const updateClaudeCodeChatArtifactsFromHistoryItems = (
  current: ClaudeCodeChatArtifacts,
  items: readonly ClaudeCodeSessionHistoryItem[]
): ClaudeCodeChatArtifacts =>
  items.reduce((artifacts, item) => {
    if (item.kind === 'user') {
      return updateClaudeCodeChatArtifactsFromUserText(artifacts, item.text);
    }

    return updateClaudeCodeChatArtifactsFromEvent(artifacts, {
      type: 'assistant',
      message: {
        content: item.parts,
      },
    });
  }, current);
