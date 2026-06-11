// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ModelEntity } from '@nemo/sdk/generated/platform/schema/ModelEntity';
import type { AgentConfig } from '@studio/components/dataViews/AgentsDataView';
import { SAMPLE_EVAL_CONFIG_PATH } from '@studio/routes/agents/AgentSuggestionsRoute/constants';
import type {
  AgentListing,
  AnalyzeInput,
  OptimizationSuggestion,
  SnapshotShape,
  SuggestionApplySpec,
} from '@studio/routes/agents/AgentSuggestionsRoute/types';

/** Fileset name for an agent's eval bundle. */
export const evalFilesetForAgent = (agentName: string): string => `${agentName}-eval`;

/** Output fileset name for an evaluation run against a deployment. */
export const evalOutputFilesetFor = (siblingAgentName: string): string =>
  `${siblingAgentName}-eval-out`;

export const snapshotModelNames = (snapshot: SnapshotShape | null): string[] => {
  if (!snapshot?.agents) return [];
  const set = new Set<string>();
  for (const entry of Object.values(snapshot.agents)) {
    for (const m of entry.modelNames) set.add(m);
  }
  return [...set];
};

export const snapshotAgentNames = (snapshot: SnapshotShape | null): string[] =>
  snapshot?.agents ? Object.keys(snapshot.agents) : [];

export const suggestionIdentity = (s: OptimizationSuggestion): string =>
  JSON.stringify({
    type: s.type,
    agent: s.agent ?? null,
    model: s.model ?? null,
  });

// Applied suggestions are preserved; fresh duplicates of an applied identity
// are dropped (don't re-prompt). Otherwise fresh analysis wins.
export const mergeWithApplied = (
  existing: OptimizationSuggestion[],
  fresh: OptimizationSuggestion[]
): OptimizationSuggestion[] => {
  const applied = existing.filter((s) => s.applied === true);
  const appliedIdentities = new Set(applied.map(suggestionIdentity));
  const freshFiltered = fresh.filter((s) => !appliedIdentities.has(suggestionIdentity(s)));
  return [...applied, ...freshFiltered];
};

export const GUARDRAIL_MODELS = [
  'nvidia-llama-3-1-nemoguard-8b-content-safety',
  'nvidia-llama-3-1-nemoguard-8b-topic-control',
  'nvidia-llama-3-1-nemotron-safety-guard-8b-v3',
] as const;

// Excluded from pickSmallerModel so a chat agent can't be downsized to a
// safety-guard / topic-control / NER model.
export const NON_CHAT_MODEL_RE =
  /nemoguard|safety[.-]?guard|content[.-]?safety|topic[.-]?control|gliner/i;

// Subset that answers Yes/No safety verdicts. Topic-control excluded — it
// classifies topic adherence, not safety.
export const CONTENT_SAFETY_MODEL_RE = /content[.-]?safety|safety[.-]?guard|gliner/i;

/** Agents with model param count ≤ this are not flagged for downsizing. */
export const SMALL_MODEL_THRESHOLD_B = 8;

/** Chars on either side of a PII regex match used for context verification. */
export const PII_CONTEXT_WINDOW = 80;

export const parseSuggestions = (text: string): OptimizationSuggestion[] => {
  const results: OptimizationSuggestion[] = [];
  for (const line of text.split('\n')) {
    if (!line.trim()) continue;
    try {
      results.push(JSON.parse(line) as OptimizationSuggestion);
    } catch {
      console.warn('parseSuggestions: skipping malformed line', line);
    }
  }
  return results;
};

export const serializeSuggestions = (suggestions: OptimizationSuggestion[]): string =>
  suggestions.map((s) => JSON.stringify(s)).join('\n');

export const severityColor = (sev: string): 'red' | 'yellow' | 'gray' => {
  if (sev === 'high') return 'red';
  if (sev === 'medium') return 'yellow';
  return 'gray';
};

export const formatActions = (actions: readonly string[]): string => actions.join(' · ');

export const capitalize = (s: string): string => s.charAt(0).toUpperCase() + s.slice(1);

export const countSeverities = (
  list: readonly OptimizationSuggestion[]
): { high: number; low: number } => {
  let high = 0;
  let low = 0;
  for (const s of list) {
    const severity = s.severity ?? 'low';
    if (severity === 'high') high += 1;
    else if (severity === 'low') low += 1;
  }
  return { high, low };
};

// e.g. `..-30b-..` → 30
export const extractBillionParams = (name: string): number | null => {
  const m = /(\d+(?:\.\d+)?)b/i.exec(name);
  return m ? parseFloat(m[1]) : null;
};

export const isNemotron = (name: string): boolean => /nemotron/i.test(name);

export const extractAgentModelNames = (config: AgentConfig | undefined): string[] => {
  const seen = new Set<string>();
  for (const llm of Object.values(config?.llms ?? {})) {
    if (llm.model_name) seen.add(llm.model_name);
  }
  return [...seen];
};

const llmIsGuarded = (llm: { base_url?: string }): boolean =>
  !!llm.base_url?.includes('/guardrails/');

export const agentHasGuardrails = (config: AgentConfig): boolean => {
  const llms = Object.values(config.llms ?? {});
  if (llms.length === 0) return false;
  return llms.every(llmIsGuarded);
};

export const extractUnguardedModelNames = (config: AgentConfig | undefined): string[] => {
  const seen = new Set<string>();
  for (const llm of Object.values(config?.llms ?? {})) {
    if (llm.model_name && !llmIsGuarded(llm)) seen.add(llm.model_name);
  }
  return [...seen];
};

interface PiiPattern {
  label: string;
  re: RegExp;
  /** Returns true if surrounding context confirms this is genuine PII. */
  verify: (context: string, match: string) => boolean;
}

// Tight, anchored — loose patterns false-positive on Unix timestamps, IDs, URLs.
export const PII_PATTERNS: readonly PiiPattern[] = [
  {
    label: 'email address',
    re: /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g,
    verify: (ctx) => !/example\.|localhost|noreply|no-reply|http/i.test(ctx),
  },
  {
    label: 'SSN',
    re: /\b\d{3}-\d{2}-\d{4}\b/g,
    verify: (ctx) => /ssn|social.?security|tin\b/i.test(ctx),
  },
  {
    label: 'phone number',
    re: /\b(\+1\s?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b/g,
    verify: (ctx, match) => {
      const idx = ctx.indexOf(match);
      const before = idx > 0 ? ctx[idx - 1] : '';
      const after = idx + match.length < ctx.length ? ctx[idx + match.length] : '';
      return !/\d/.test(before) && !/\d/.test(after);
    },
  },
  {
    label: 'credit card',
    re: /\b(?:\d{4}[-\s]){3}\d{4}\b/g,
    verify: (ctx) => /card|visa|master|amex|discover|payment|cvv/i.test(ctx),
  },
];

export const scanForPii = (text: string): string[] => {
  const hits: string[] = [];
  for (const { label, re, verify } of PII_PATTERNS) {
    re.lastIndex = 0;
    let m: RegExpExecArray | null;
    while ((m = re.exec(text)) !== null) {
      const start = Math.max(0, m.index - PII_CONTEXT_WINDOW);
      const end = Math.min(text.length, m.index + m[0].length + PII_CONTEXT_WINDOW);
      const context = text.slice(start, end);
      if (verify(context, m[0])) {
        hits.push(label);
        break;
      }
    }
  }
  return hits;
};

// Emit one suggestion per unguarded LLM so (type, agent, model) identity is
// stable when a mixed config is partially fixed.
const buildGuardrailsSuggestions = (agent: AgentListing): OptimizationSuggestion[] => {
  const unguarded = extractUnguardedModelNames(agent.config);
  return unguarded.map((modelName) => ({
    type: 'guardrails',
    title: `No guardrails on ${agent.name} (${modelName})`,
    detail: `Agent "${agent.name}" routes "${modelName}" directly through the inference gateway with no guardrails layer.`,
    agent: agent.name,
    model: modelName,
    severity: 'high',
    suggested_actions: [
      'nemo guardrails configs create ...',
      `Recommended models: ${GUARDRAIL_MODELS.join(', ')}`,
    ],
  }));
};

// Largest smaller-than-current candidate, preferring Nemotron.
const pickSmallerModel = (
  models: ModelEntity[],
  currentParamsB: number
): ModelEntity | undefined => {
  const candidates = models.filter((m) => {
    const p = extractBillionParams(m.name);
    if (p === null || p >= currentParamsB) return false;
    return !NON_CHAT_MODEL_RE.test(m.name);
  });
  if (candidates.length === 0) return undefined;

  const nemotron = candidates.filter((m) => isNemotron(m.name));
  const pool = nemotron.length > 0 ? nemotron : candidates;
  return pool.sort(
    (a, b) => (extractBillionParams(b.name) ?? 0) - (extractBillionParams(a.name) ?? 0)
  )[0];
};

export const slugForAgentName = (modelName: string): string =>
  modelName
    .toLowerCase()
    .replace(/[^a-z0-9-]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-+|-+$/g, '');

const SIBLING_SUFFIX_ALPHABET = 'abcdefghijklmnopqrstuvwxyz0123456789';
const SIBLING_SUFFIX_LENGTH = 5;

/** 5-char base36 random suffix appended to sibling agent names so re-applies don't 409. */
export const randomSiblingSuffix = (): string => {
  // Prefer crypto.getRandomValues over Math.random — test environments stub
  // Math.random for determinism, but the runtime path needs uncorrelated bytes
  // across rapid re-applies.
  const bytes = new Uint8Array(SIBLING_SUFFIX_LENGTH);
  crypto.getRandomValues(bytes);
  let out = '';
  for (const b of bytes) out += SIBLING_SUFFIX_ALPHABET[b % SIBLING_SUFFIX_ALPHABET.length];
  return out;
};

// Deep-clones config and swaps llms[*].model_name === oldModel → newModel.
export const swapModelInConfig = (
  config: AgentConfig,
  oldModel: string,
  newModel: string
): Record<string, unknown> => {
  const cloned = JSON.parse(JSON.stringify(config)) as {
    llms?: Record<string, { model_name?: string }>;
  };
  for (const llm of Object.values(cloned.llms ?? {})) {
    if (llm.model_name === oldModel) llm.model_name = newModel;
  }
  return cloned as Record<string, unknown>;
};

const buildModelOptimizationSuggestion = (
  agent: AgentListing,
  modelName: string,
  currentParamsB: number,
  best: ModelEntity,
  workspace: string
): OptimizationSuggestion => {
  // Sibling-name pattern used by the canonical SKILL example: keep the
  // original agent name as a stem and append a model slug. A short random
  // suffix is appended so re-applying (or applying after a partial-failure
  // rollback) doesn't 409 on the existing sibling. Identity dedupe keys off
  // (type, agent, source-model), not the sibling name, so the random suffix
  // doesn't break re-run merge.
  const suffix = randomSiblingSuffix();
  const siblingName = `${agent.name}-${slugForAgentName(best.name)}-${suffix}`;
  const siblingConfig = agent.config
    ? swapModelInConfig(agent.config, modelName, best.name)
    : undefined;
  // The eval fileset is shared across siblings of the same parent agent so
  // re-applying with a different target model reuses the same dataset / judge
  // config. The optimizer hook seeds the fileset with the bundled sample
  // before submitting the apply array.
  const evalFileset = evalFilesetForAgent(agent.name);
  const evalOutputFileset = evalOutputFilesetFor(siblingName);
  const apply: SuggestionApplySpec[] | undefined = siblingConfig
    ? [
        {
          method: 'POST',
          path: `/apis/agents/v2/workspaces/${workspace}/agents`,
          body: { name: siblingName, config: siblingConfig },
        },
        {
          method: 'POST',
          path: `/apis/agents/v2/workspaces/${workspace}/deployments`,
          body: { agent: siblingName },
        },
        {
          method: 'POST',
          path: `/apis/agents/v2/workspaces/${workspace}/jobs/evaluate`,
          body: {
            spec: {
              agent: siblingName,
              eval_config: SAMPLE_EVAL_CONFIG_PATH,
              eval_config_fileset: evalFileset,
              output: evalOutputFileset,
            },
          },
        },
      ]
    : undefined;
  return {
    type: 'model_optimization',
    // Source model in title so multi-LLM agents get distinct titles.
    title: `Smaller model available for ${agent.name}: ${modelName} → ${best.name}`,
    detail: `Agent uses "${modelName}" (${currentParamsB}B). "${best.name}" is available${
      isNemotron(best.name) ? ' (Nemotron)' : ''
    } with fewer parameters. Run an evaluation against the smaller model first to confirm task quality.`,
    agent: agent.name,
    // Source (currently-deployed) model — drives the tile badge and stabilizes
    // (type, agent, model) identity across reruns.
    model: modelName,
    suggested_actions: [
      `nemo agents evaluate --agent ${agent.name} --model ${best.name}`,
      'Or use switchyard for automatic model routing based on task profile',
    ],
    apply,
    apply_description: apply
      ? `Creates "${siblingName}" with "${best.name}", deploys it, and runs an evaluation against the bundled sample dataset (fileset "${evalFileset}").`
      : undefined,
  };
};

const buildDataSafetySuggestion = (
  piiHits: string[],
  contentSafetyRisk: boolean
): OptimizationSuggestion => {
  const detail = [
    piiHits.length > 0 ? `PII patterns (${piiHits.join(', ')}) found in traces.` : '',
    contentSafetyRisk ? 'Content safety model flagged unsafe content in traces.' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return {
    type: 'data_safety',
    title: 'Potential unsafe data in telemetry',
    detail,
    severity: 'high',
    suggested_actions: ['nemo data safe-synthesizer ...', 'Enable PII anonymisation'],
  };
};

const buildNewModelSuggestion = (modelName: string): OptimizationSuggestion => ({
  type: 'new_model_scan',
  title: `New model available: ${modelName}`,
  detail: `Model "${modelName}" appeared since the last optimizer run. Consider running Auditor and Evaluator against it.`,
  model: modelName,
  suggested_actions: [
    `nemo auditor targets create <target> -d '{"model": "${modelName}", "type": "<type>"}'`,
    `nemo auditor audit run --spec '{"config": "default/<config>", "target": "default/<target>"}'`,
    `nemo evaluation jobs create --model ${modelName}`,
  ],
});

// Pure — no I/O, no React.
export const analyze = ({
  agents,
  models,
  piiSampleText,
  contentSafetyRisk,
  prevSnapshot,
  workspace,
}: AnalyzeInput): OptimizationSuggestion[] => {
  const suggestions: OptimizationSuggestion[] = [];

  for (const agent of agents) {
    if (!agent.config || agentHasGuardrails(agent.config)) continue;
    suggestions.push(...buildGuardrailsSuggestions(agent));
  }

  // One suggestion per oversized LLM per agent.
  for (const agent of agents) {
    for (const modelName of extractAgentModelNames(agent.config)) {
      const params = extractBillionParams(modelName);
      if (params === null || params <= SMALL_MODEL_THRESHOLD_B) continue;

      const best = pickSmallerModel(models, params);
      if (!best) continue;
      suggestions.push(buildModelOptimizationSuggestion(agent, modelName, params, best, workspace));
    }
  }

  const piiHits = scanForPii(piiSampleText);
  if (piiHits.length > 0 || contentSafetyRisk) {
    suggestions.push(buildDataSafetySuggestion(piiHits, contentSafetyRisk));
  }

  const prevModelNames = new Set(snapshotModelNames(prevSnapshot));
  if (prevModelNames.size > 0) {
    for (const model of models) {
      if (prevModelNames.has(model.name)) continue;
      suggestions.push(buildNewModelSuggestion(model.name));
    }
  }

  return suggestions;
};
