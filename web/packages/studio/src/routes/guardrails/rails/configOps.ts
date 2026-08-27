// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RailsConfig, TaskPrompt } from '@nemo/sdk/generated/platform/schema';
import type { RailScope } from '@studio/routes/guardrails/rails/types';

/**
 * Immutable edits to the parts of a `RailsConfig` that rail definitions own: the flow
 * lists under `rails.<scope>` and the entries in `prompts[]`.
 *
 * Every helper returns a new config and leaves everything it wasn't asked about alone —
 * a guardrail config carries plenty we don't model, and it has to survive a round trip
 * through the editor untouched.
 */

/** Flow names configured for a stage, in execution order. */
export const stageFlows = (data: RailsConfig, scope: RailScope): string[] =>
  data.rails?.[scope]?.flows ?? [];

export const hasFlow = (data: RailsConfig, scope: RailScope, flow: string): boolean =>
  stageFlows(data, scope).includes(flow);

/** Add a flow to a stage. Idempotent, and appends so existing order is preserved. */
export const withFlow = (data: RailsConfig, scope: RailScope, flow: string): RailsConfig => {
  if (hasFlow(data, scope, flow)) return data;
  return withStageFlows(data, scope, [...stageFlows(data, scope), flow]);
};

/** Remove a flow from a stage. Idempotent. */
export const withoutFlow = (data: RailsConfig, scope: RailScope, flow: string): RailsConfig => {
  if (!hasFlow(data, scope, flow)) return data;
  return withStageFlows(
    data,
    scope,
    stageFlows(data, scope).filter((existing) => existing !== flow)
  );
};

/**
 * Replace a stage's flow list.
 *
 * The stage object is kept even when the list empties, because it can carry settings we
 * don't own (`parallel`, `streaming`, `apply_to_reasoning_traces`) that must not be
 * dropped just because the last rail was switched off.
 */
const withStageFlows = (data: RailsConfig, scope: RailScope, flows: string[]): RailsConfig => ({
  ...data,
  rails: {
    ...data.rails,
    [scope]: { ...data.rails?.[scope], flows },
  },
});

export const findPrompt = (data: RailsConfig, task: string): TaskPrompt | undefined =>
  data.prompts?.find((prompt) => prompt.task === task);

/** Insert or replace the prompt for a task, preserving the position of an existing one. */
export const withPrompt = (data: RailsConfig, prompt: TaskPrompt): RailsConfig => {
  const prompts = data.prompts ?? [];
  const index = prompts.findIndex((existing) => existing.task === prompt.task);
  return {
    ...data,
    prompts:
      index === -1
        ? [...prompts, prompt]
        : prompts.map((existing, i) => (i === index ? prompt : existing)),
  };
};

/** Remove a task's prompt. Drops `prompts` entirely once it empties, matching the API shape. */
export const withoutPrompt = (data: RailsConfig, task: string): RailsConfig => {
  const prompts = data.prompts ?? [];
  if (!prompts.some((prompt) => prompt.task === task)) return data;
  const next = prompts.filter((prompt) => prompt.task !== task);
  return { ...data, prompts: next.length ? next : undefined };
};

/** Set a prompt's body, creating the entry if the task doesn't have one yet. */
export const withPromptContent = (data: RailsConfig, task: string, content: string): RailsConfig =>
  withPromptFields(data, task, { content });

/** Merge fields into a task's prompt, creating the entry if it doesn't have one yet. */
export const withPromptFields = (
  data: RailsConfig,
  task: string,
  patch: Partial<Omit<TaskPrompt, 'task'>>
): RailsConfig => withPrompt(data, { ...findPrompt(data, task), task, ...patch });
