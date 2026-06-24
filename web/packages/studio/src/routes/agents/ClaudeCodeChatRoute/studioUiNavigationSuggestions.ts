// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { featureFlags } from '@studio/constants/featureFlags';
import type { FeatureFlags } from '@studio/constants/featureFlags/featureFlags';
import {
  getAgentEvaluationsListRoute,
  getAgentMonitorRoute,
  getAgentOptimizationsRoute,
  getAgentsListRoute,
  getDataDesignerJobListRoute,
  getEvaluationResultsRoute,
  getGuardrailsRoute,
  getIntakeRoute,
  getModelCompareRoute,
  getNewDataDesignerJobRoute,
  getNewFilesetRoute,
  getNewSafeSynthesizerRoute,
  getPromptTuningFormRoute,
  getSecretsRoute,
  getWorkspaceBaseModelsRoute,
  getWorkspaceCustomizationJobListRoute,
  getWorkspaceDeploymentsRoute,
  getWorkspaceInferenceProvidersRoute,
  getWorkspaceJobsRoute,
  getWorkspaceMembersRoute,
  getWorkspaceNewCustomizationJobRoute,
  getWorkspaceSafeSynthesizerRoute,
  getWorkspaceSettingsRoute,
} from '@studio/routes/utils';

type FeatureFlagName = keyof FeatureFlags;

export interface StudioUiNavigationSuggestion {
  id: string;
  title: string;
  description: string;
  href: string;
}

interface StudioUiDestination {
  id: string;
  title: string;
  description: string;
  getHref: (workspace: string) => string;
  patterns: readonly RegExp[];
  requiredFeatureFlags?: readonly FeatureFlagName[];
}

const STUDIO_UI_DESTINATIONS: readonly StudioUiDestination[] = [
  {
    id: 'safe-synthesizer-new',
    title: 'Open Safe Synthesizer',
    description: 'Studio has a guided UI for generating safe synthetic datasets.',
    getHref: getNewSafeSynthesizerRoute,
    requiredFeatureFlags: ['safeSynthesizerEnabled'],
    patterns: [
      /\bsafe[-\s]?synthesizer\b/i,
      /\bsynthetic (data|dataset|datasets)\b/i,
      /\bsynthesi[sz]e (data|dataset|datasets)\b/i,
    ],
  },
  {
    id: 'agent-evaluations',
    title: 'Open Agent Evaluations',
    description: 'Studio has a UI for submitting and reviewing agent evaluation jobs.',
    getHref: getAgentEvaluationsListRoute,
    requiredFeatureFlags: ['agentsEnabled'],
    patterns: [
      /\bagent (eval|evaluation|evaluations)\b/i,
      /\bevaluat(e|ing|ion)s? (an? )?agent\b/i,
      /\brun (an? )?(eval|evaluation) (for|on) (an? )?agent\b/i,
    ],
  },
  {
    id: 'agent-optimizations',
    title: 'Open Agent Suggestions',
    description: 'Studio has a UI for generating optimization suggestions for deployed agents.',
    getHref: getAgentOptimizationsRoute,
    requiredFeatureFlags: ['agentsEnabled'],
    patterns: [
      /\boptimi[sz]e (an? )?agent\b/i,
      /\b(agent|agents).*\b(cheaper|faster|smaller|right[-\s]?size)\b/i,
      /\bmodel sizing\b/i,
      /\bsuggestions? for (an? )?agent\b/i,
    ],
  },
  {
    id: 'agent-monitor',
    title: 'Open Agent Monitor',
    description: 'Studio has a monitor UI for agent telemetry, logs, and token usage.',
    getHref: getAgentMonitorRoute,
    requiredFeatureFlags: ['agentsEnabled'],
    patterns: [
      /\bmonitor (an? )?agent\b/i,
      /\bagent (monitor|telemetry|logs|traces|usage)\b/i,
      /\btoken usage\b/i,
    ],
  },
  {
    id: 'guardrails',
    title: 'Open Guardrails',
    description: 'Studio has a UI for managing NeMo Guardrails configurations.',
    getHref: getGuardrailsRoute,
    requiredFeatureFlags: ['guardrailsEnabled'],
    patterns: [
      /\bguardrails?\b/i,
      /\bcontent safety\b/i,
      /\bjailbreak\b/i,
      /\bpii (redaction|guard|protection)\b/i,
    ],
  },
  {
    id: 'data-designer-new',
    title: 'Open Data Designer',
    description: 'Studio has a Data Designer UI for creating and transforming datasets.',
    getHref: getNewDataDesignerJobRoute,
    requiredFeatureFlags: ['dataDesignerEnabled'],
    patterns: [
      /\bdata designer\b/i,
      /\bgenerate (data|dataset|datasets)\b/i,
      /\bcreate (a )?(dataset|datasets)\b/i,
      /\btransform (a )?(dataset|datasets)\b/i,
    ],
  },
  {
    id: 'fileset-new',
    title: 'Open Fileset Upload',
    description: 'Studio has a UI for creating filesets and uploading files.',
    getHref: getNewFilesetRoute,
    requiredFeatureFlags: ['datasetsEnabled'],
    patterns: [
      /\bcreate (a )?fileset\b/i,
      /\bnew fileset\b/i,
      /\bupload (a )?(file|files|dataset|datasets)\b/i,
      /\bimport (a )?(file|files|dataset|datasets)\b/i,
    ],
  },
  {
    id: 'inference-providers',
    title: 'Open Inference Providers',
    description: 'Studio has a UI for adding and managing inference providers.',
    getHref: getWorkspaceInferenceProvidersRoute,
    requiredFeatureFlags: ['inferenceProviderEnabled'],
    patterns: [
      /\binference provider\b/i,
      /\bmodel provider\b/i,
      /\b(add|create|configure|connect|manage|register) (an? )?(provider|inference endpoint)\b/i,
      /\b(connect|configure) (openai|nvidia|nim|build)\b/i,
    ],
  },
  {
    id: 'secrets',
    title: 'Open Secrets',
    description: 'Studio has a UI for creating and managing workspace secrets.',
    getHref: getSecretsRoute,
    requiredFeatureFlags: ['secretsEnabled'],
    patterns: [
      /\b(add|create|manage|store|update) (an? )?(secret|secrets)\b/i,
      /\b(add|create|manage|store|update) (an? )?(api key|credential|credentials|token)\b/i,
      /\bworkspace secret(s)?\b/i,
    ],
  },
  {
    id: 'prompt-tuning',
    title: 'Open Prompt Tuning',
    description: 'Studio has a UI for creating prompt-tuned models.',
    getHref: getPromptTuningFormRoute,
    requiredFeatureFlags: ['customizerEnabled'],
    patterns: [/\bprompt[-\s]?tun(e|ing)\b/i],
  },
  {
    id: 'fine-tuning',
    title: 'Open Fine-Tuning',
    description: 'Studio has a UI for creating fine-tuned custom models.',
    getHref: getWorkspaceNewCustomizationJobRoute,
    requiredFeatureFlags: ['customizerEnabled'],
    patterns: [
      /\bfine[-\s]?tun(e|ing)\b/i,
      /\bfinetun(e|ing)\b/i,
      /\btrain (a )?(model|custom model)\b/i,
      /\bcustomi[sz]e (a )?model\b/i,
    ],
  },
  {
    id: 'model-playground',
    title: 'Open Playground',
    description: 'Studio has a playground UI for chatting with and comparing models.',
    getHref: getModelCompareRoute,
    requiredFeatureFlags: ['modelCompareEnabled'],
    patterns: [
      /\bplayground\b/i,
      /\bcompare (models|model responses)\b/i,
      /\bchat with (a )?model\b/i,
    ],
  },
  {
    id: 'model-deployments',
    title: 'Open Deployments',
    description: 'Studio has a UI for managing model deployments.',
    getHref: getWorkspaceDeploymentsRoute,
    requiredFeatureFlags: ['deploymentsEnabled'],
    patterns: [
      /\bmodel deployments?\b/i,
      /\bdeploy (a )?model\b/i,
      /\bserve (a )?model\b/i,
      /\bmodel endpoint\b/i,
    ],
  },
  {
    id: 'base-models',
    title: 'Open Base Models',
    description: 'Studio has a UI for browsing base models and model details.',
    getHref: getWorkspaceBaseModelsRoute,
    requiredFeatureFlags: ['baseModelsEnabled'],
    patterns: [
      /\bbase models?\b/i,
      /\bmodel catalog\b/i,
      /\bbrowse models?\b/i,
      /\blist models?\b/i,
    ],
  },
  {
    id: 'custom-models',
    title: 'Open Custom Models',
    description: 'Studio has a UI for managing custom models and customization jobs.',
    getHref: getWorkspaceCustomizationJobListRoute,
    requiredFeatureFlags: ['customizerEnabled'],
    patterns: [/\bcustom models?\b/i, /\bcustomization jobs?\b/i],
  },
  {
    id: 'agents',
    title: 'Open Agents',
    description: 'Studio has a UI for viewing agents and managing their deployments.',
    getHref: getAgentsListRoute,
    requiredFeatureFlags: ['agentsEnabled'],
    patterns: [
      /\bmanage agents?\b/i,
      /\bview agents?\b/i,
      /\bcreate example agent\b/i,
      /\bclone (an? )?agent\b/i,
      /\bchat with (an? )?agent\b/i,
      /\bdeploy (an? )?agent\b/i,
    ],
  },
  {
    id: 'evaluations',
    title: 'Open Evaluations',
    description: 'Studio has a UI for reviewing model evaluation results.',
    getHref: getEvaluationResultsRoute,
    requiredFeatureFlags: ['evaluatorEnabled'],
    patterns: [
      /\bevaluat(e|ing|ion)s? (a )?model\b/i,
      /\bmodel (eval|evaluation|evaluations)\b/i,
      /\bevaluation results?\b/i,
    ],
  },
  {
    id: 'safe-synthesizer',
    title: 'Open Safe Synthesizer',
    description: 'Studio has a UI for monitoring safe synthetic data jobs.',
    getHref: getWorkspaceSafeSynthesizerRoute,
    requiredFeatureFlags: ['safeSynthesizerEnabled'],
    patterns: [/\bsafe synth(esizer)? jobs?\b/i],
  },
  {
    id: 'data-designer',
    title: 'Open Data Designer',
    description: 'Studio has a UI for managing Data Designer jobs.',
    getHref: getDataDesignerJobListRoute,
    requiredFeatureFlags: ['dataDesignerEnabled'],
    patterns: [/\bdata designer jobs?\b/i],
  },
  {
    id: 'jobs',
    title: 'Open Jobs',
    description: 'Studio has a UI for viewing workspace jobs.',
    getHref: getWorkspaceJobsRoute,
    requiredFeatureFlags: ['jobsEnabled'],
    patterns: [/\bworkspace jobs?\b/i, /\bjob history\b/i],
  },
  {
    id: 'annotation',
    title: 'Open Annotation',
    description: 'Studio has a UI for inspecting intake traces and annotations.',
    getHref: getIntakeRoute,
    requiredFeatureFlags: ['intakeEnabled'],
    patterns: [/\bannotation\b/i, /\bintake traces?\b/i, /\btrace review\b/i],
  },
  {
    id: 'members',
    title: 'Open Members',
    description: 'Studio has a UI for managing workspace members.',
    getHref: getWorkspaceMembersRoute,
    requiredFeatureFlags: ['membersEnabled'],
    patterns: [/\bworkspace members?\b/i, /\badd (a )?member\b/i, /\buser access\b/i],
  },
  {
    id: 'settings',
    title: 'Open Settings',
    description: 'Studio has a UI for workspace settings.',
    getHref: getWorkspaceSettingsRoute,
    requiredFeatureFlags: ['settingsEnabled'],
    patterns: [/\bworkspace settings?\b/i, /\b(open|change|manage|update) settings\b/i],
  },
];

const isDestinationEnabled = (destination: StudioUiDestination): boolean =>
  destination.requiredFeatureFlags?.every((flag) => featureFlags[flag] !== false) ?? true;

export const getStudioUiNavigationSuggestion = (
  prompt: string,
  workspace: string
): StudioUiNavigationSuggestion | undefined => {
  const trimmedPrompt = prompt.trim();
  if (!trimmedPrompt) return undefined;

  for (const destination of STUDIO_UI_DESTINATIONS) {
    if (!isDestinationEnabled(destination)) continue;
    if (!destination.patterns.some((pattern) => pattern.test(trimmedPrompt))) continue;

    return {
      id: destination.id,
      title: destination.title,
      description: destination.description,
      href: destination.getHref(workspace),
    };
  }

  return undefined;
};
