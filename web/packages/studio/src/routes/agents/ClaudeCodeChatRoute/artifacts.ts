// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type {
  ClaudeCodeChatArtifacts,
  ClaudeCodeChatFileArtifact,
  ClaudeCodeChatJobArtifact,
  ClaudeCodeChatLinkArtifact,
  ClaudeCodeChatSelectionArtifact,
  ClaudeCodeSessionHistoryItem,
} from '@studio/routes/agents/ClaudeCodeChatRoute/types';
import { getJobProgressDetailRoute } from '@studio/routes/agents/ClaudeCodeChatRoute/utils/jobProgress';

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
const STUDIO_LINK_PATH_TEMPLATES: Record<string, string> = {
  workspace: '/workspaces/{workspace}',
  dashboard: '/workspaces/{workspace}/dashboard',
  code_agent: '/workspaces/{workspace}/dashboard/code-agent',
  agents: '/workspaces/{workspace}/agents',
  agent: '/workspaces/{workspace}/agents/{name}',
  agent_chat: '/workspaces/{workspace}/agents/{name}?tab=chat-playground',
  agent_deployments: '/workspaces/{workspace}/agents',
  agent_deployment: '/workspaces/{workspace}/agents/{name}',
  agent_evaluations: '/workspaces/{workspace}/agents/evaluations',
  agent_evaluation: '/workspaces/{workspace}/agents/evaluations/{name}',
  agent_monitor: '/workspaces/{workspace}/agents/monitor',
  agent_optimizations: '/workspaces/{workspace}/agents/suggestions',
  base_models: '/workspaces/{workspace}/base-models',
  base_model: '/workspaces/{workspace}/base-models/{name}',
  base_model_chat: '/workspaces/{workspace}/base-models/{name}?tab=chat-playground',
  evaluation: '/workspaces/{workspace}/evaluation',
  evaluation_metrics: '/workspaces/{workspace}/evaluation/metrics',
  evaluation_metric_new: '/workspaces/{workspace}/evaluation/metrics/new',
  evaluation_run: '/workspaces/{workspace}/evaluation/metrics/run',
  evaluation_metric: '/workspaces/{workspace}/evaluation/metrics/{name}',
  evaluation_metric_run: '/workspaces/{workspace}/evaluation/metrics/{name}/run',
  evaluation_benchmarks: '/workspaces/{workspace}/evaluation/benchmarks',
  evaluation_benchmark: '/workspaces/{workspace}/evaluation/benchmarks/{name}',
  evaluation_results: '/workspaces/{workspace}/evaluation/results',
  evaluation_result: '/workspaces/{workspace}/evaluation/results/{name}',
  customizations: '/workspaces/{workspace}/customizations',
  customization_new: '/workspaces/{workspace}/customizations/fine-tuned/new',
  customization: '/workspaces/{workspace}/customizations/{name}',
  prompt_tuning: '/workspaces/{workspace}/customizations/prompt-tuned/new',
  model_chat: '/workspaces/{workspace}/model-compare',
  jobs: '/workspaces/{workspace}/jobs',
  job: '/workspaces/{workspace}/jobs/{name}',
  filesets: '/workspaces/{workspace}/filesets',
  fileset_new: '/workspaces/{workspace}/filesets/new',
  fileset_panel: '/workspaces/{workspace}/filesets/{name}',
  fileset: '/workspaces/{workspace}/filesets/{name}/detail',
  fileset_file: '/workspaces/{workspace}/filesets/{name}/file/{file_path}',
  deployments: '/workspaces/{workspace}/deployments',
  deployment: '/workspaces/{workspace}/deployments/{name}/details',
  inference_providers: '/workspaces/{workspace}/inference-providers',
  guardrails: '/workspaces/{workspace}/guardrails',
  secrets: '/workspaces/{workspace}/secrets',
  intake: '/workspaces/{workspace}/intake',
  intake_traces: '/workspaces/{workspace}/intake/traces',
  intake_spans: '/workspaces/{workspace}/intake/spans',
  intake_trace: '/workspaces/{workspace}/intake/traces/{name}',
  intake_span: '/workspaces/{workspace}/intake/spans/{name}',
  data_designer: '/workspaces/{workspace}/data-designer',
  data_designer_new: '/workspaces/{workspace}/data-designer/new',
  data_designer_job: '/workspaces/{workspace}/data-designer/{name}',
  safe_synthesizer: '/workspaces/{workspace}/safe-synthesizer',
  safe_synthesizer_new: '/workspaces/{workspace}/safe-synthesizer/new',
  safe_synthesizer_job: '/workspaces/{workspace}/safe-synthesizer/job/{name}',
  safe_synthesizer_report: '/workspaces/{workspace}/safe-synthesizer/job/{name}/report',
  settings: '/workspaces/{workspace}/settings',
  members: '/workspaces/{workspace}/members',
  experiment: '/workspaces/{workspace}/experiment',
  experiment_group: '/workspaces/{workspace}/experiment/{name}',
  experiment_detail: '/workspaces/{workspace}/experiment/{name}/{experiment_name}',
};
const STUDIO_LINK_ARGUMENT_ALIASES = {
  name: [
    'resource_name',
    'resourceName',
    'id',
    'job_name',
    'jobName',
    'agent_name',
    'agentName',
    'model_name',
    'modelName',
    'fileset_id',
    'filesetId',
    'fileset_name',
    'filesetName',
    'deployment_name',
    'deploymentName',
    'trace_id',
    'traceId',
    'span_id',
    'spanId',
    'experiment_group_id',
    'experimentGroupId',
  ],
  experiment_name: ['experimentName', 'experiment_id', 'experimentId'],
  file_path: ['file', 'filePath', 'file_path_encoded', 'filePathEncoded', 'path'],
} satisfies Record<'name' | 'experiment_name' | 'file_path', readonly string[]>;

export const createEmptyClaudeCodeChatArtifacts = (): ClaudeCodeChatArtifacts => ({
  selections: [],
  files: [],
  links: [],
  jobs: [],
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

const decodeEncodedFilePath = (value: string): string => {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
};

const normalizeStudioLinkDestination = (value: string | undefined): string | undefined => {
  const normalized = value
    ?.trim()
    .toLowerCase()
    .replace(/[-\s]+/g, '_');
  return normalized && STUDIO_LINK_PATH_TEMPLATES[normalized] ? normalized : undefined;
};

const getStudioLinkArgument = (
  input: Record<string, unknown>,
  argumentName: keyof typeof STUDIO_LINK_ARGUMENT_ALIASES
): string | undefined => {
  for (const key of [argumentName, ...STUDIO_LINK_ARGUMENT_ALIASES[argumentName]]) {
    const value = getString(input[key]);
    if (!value) continue;
    if (
      argumentName === 'file_path' &&
      (key === 'file_path_encoded' || key === 'filePathEncoded')
    ) {
      return decodeEncodedFilePath(value);
    }
    return value;
  }

  return undefined;
};

const buildStudioLinkHrefFromInput = (
  input: Record<string, unknown>,
  workspace: string | undefined
): string | undefined => {
  const explicitHref = getString(input.href) ?? getString(input.url);
  if (explicitHref) return explicitHref;

  const destination = normalizeStudioLinkDestination(
    getString(input.destination) ?? getString(input.page) ?? getString(input.resource_type)
  );
  const template = destination ? STUDIO_LINK_PATH_TEMPLATES[destination] : undefined;
  const workspaceValue = getString(input.workspace) ?? workspace;
  if (!template || !workspaceValue) return undefined;

  const values: Record<string, string> = {
    workspace: encodeURIComponent(workspaceValue),
  };

  for (const argumentName of ['name', 'experiment_name', 'file_path'] as const) {
    if (!template.includes(`{${argumentName}}`)) continue;

    const value = getStudioLinkArgument(input, argumentName);
    if (!value) return undefined;

    values[argumentName] = encodeURIComponent(value);
  }

  return template.replace(
    /\{(workspace|name|experiment_name|file_path)\}/g,
    (_match, key: string) => values[key] ?? ''
  );
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
  jobs: [...artifacts.jobs],
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
  } else if (cleanedSelection.label === 'Model') {
    artifacts.model = cleanedSelection.value;
    artifacts.model_source = 'selection';
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
  const existingIndex = artifacts.links.findIndex(
    (item) => item.label === link.label && item.destination === link.destination
  );
  if (existingIndex >= 0) {
    artifacts.links[existingIndex] = {
      ...artifacts.links[existingIndex],
      href: link.href ?? artifacts.links[existingIndex]?.href,
    };
    return;
  }
  artifacts.links.push(link);
};

const upsertJob = (artifacts: ClaudeCodeChatArtifacts, job: ClaudeCodeChatJobArtifact) => {
  const existingIndex = artifacts.jobs.findIndex((item) => item.name === job.name);
  if (existingIndex >= 0) {
    const existingJob = artifacts.jobs[existingIndex];
    if (!existingJob) return;

    artifacts.jobs[existingIndex] = {
      ...existingJob,
      ...job,
      job_type: job.job_type ?? existingJob.job_type,
      source: job.source ?? existingJob.source,
      href: job.href ?? existingJob.href,
    };
    return;
  }
  artifacts.jobs.push(job);
};

const buildJobHref = (
  jobName: string,
  input: Record<string, unknown>,
  workspace: string | undefined
): string | undefined => {
  const explicitHref = getString(input.href) ?? getString(input.url);
  if (explicitHref) return explicitHref;
  if (!workspace) return undefined;

  return getJobProgressDetailRoute({
    jobName,
    jobType: getString(input.job_type) ?? getString(input.type),
    source: getString(input.source),
    workspace,
  });
};

const recordJobArtifact = (artifacts: ClaudeCodeChatArtifacts, input: Record<string, unknown>) => {
  const name = getString(input.job_name) ?? getString(input.name);
  if (!name) return;

  upsertJob(artifacts, {
    name,
    job_type: getString(input.job_type) ?? getString(input.type),
    source: getString(input.source),
    href: buildJobHref(name, input, artifacts.workspace),
  });
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
    const href = buildStudioLinkHrefFromInput(input, artifacts.workspace);
    if (label) appendLink(artifacts, { label, destination, href });
    if (destination === 'job') recordJobArtifact(artifacts, input);
  }

  if ((toolName === 'job_progress' || toolName.endsWith('__job_progress')) && isRecord(input)) {
    recordJobArtifact(artifacts, input);
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
