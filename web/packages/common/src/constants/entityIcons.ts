// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  Bot,
  Boxes,
  ChartBar,
  DatabaseCheck,
  FileStack,
  FlaskConical,
  FolderOpen,
  Form,
  GitCompare,
  Lightbulb,
  ListChecks,
  ListTree,
  LockKeyhole,
  Logs,
  Metronome,
  Radar,
  Rocket,
  ShieldCheck,
  ShieldKeyhole,
  UserPen,
  UsersRound,
  Waypoints,
  type LucideIcon,
} from 'lucide-react';

/**
 * The single canonical glyph for every entity Studio represents.
 *
 * One entity means one icon, everywhere it appears — sidebar nav, route header,
 * empty state, primary CTA. Import from here rather than reaching for
 * `lucide-react` at the callsite: a locally chosen glyph is how the surfaces
 * drifted apart in the first place (ASTD-447).
 *
 * Choosing a glyph for a new entity:
 * - Reuse the parent's glyph family for a sub-entity (`guardrails` /
 *   `guardrailChecks`, `telemetryTraces` / `telemetrySpans`) so the
 *   relationship reads visually.
 * - Never reuse a glyph already spoken for by an unrelated entity. Two entities
 *   on one glyph means neither one owns it.
 */
export const ENTITY_ICONS = {
  // Agents
  agents: Bot,
  agentMonitorRuns: Bot,

  // Models
  baseModels: Boxes,
  customModels: Metronome,
  deployments: Rocket,
  virtualModels: Waypoints,
  inferenceProviders: Radar,

  // Data
  filesets: FileStack,
  filesetFiles: FolderOpen,
  anonymizerJobs: UserPen,
  dataDesignerJobs: Form,
  safeSynthesizerJobs: DatabaseCheck,

  // Governance. Keyhole locks a config down; the check verifies one.
  guardrails: ShieldKeyhole,
  guardrailChecks: ShieldCheck,

  // Evaluation
  evaluationResults: ChartBar,
  agentEvaluations: ChartBar,
  evaluationSessions: ChartBar,
  experiments: FlaskConical,
  insightExperiments: FlaskConical,
  evalComparison: GitCompare,

  // Observability
  optimizerInsights: Lightbulb,
  telemetryTraces: ListTree,
  insightTraces: ListTree,
  telemetrySpans: Logs,

  // System
  jobs: ListChecks,
  secrets: LockKeyhole,
  members: UsersRound,
} as const satisfies Record<string, LucideIcon>;

/** Every entity with a canonical icon. Also keys the empty-state registry. */
export type EntityKey = keyof typeof ENTITY_ICONS;
