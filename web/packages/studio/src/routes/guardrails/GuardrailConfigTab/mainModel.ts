// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { Model } from '@nemo/sdk/generated/platform/schema';
import { GUARDRAIL_DEFAULT_ENGINE } from '@studio/constants/constants';

/**
 * The model entry the generation LLM is read from. Every other entry in `models[]` is a
 * task LLM (content-safety, topic-control, embeddings) that a specific rail addresses by
 * `$model=` in its flow — never the model completions are generated against.
 */
export const MAIN_MODEL_TYPE = 'main';

/** The `main` model entry, or undefined when the config declares none. */
export const getMainModel = (models: Model[] | undefined): Model | undefined =>
  models?.find((model) => model.type === MAIN_MODEL_TYPE);

/** Name of the `main` model, or '' when there is no entry or it carries no name. */
export const getMainModelName = (models: Model[] | undefined): string =>
  getMainModel(models)?.model ?? '';

/**
 * Return a new models array with the `main` entry's name set to `name`, preserving every
 * other entry and the original order.
 *
 * - No main entry yet + non-empty `name` → one is appended with the default engine.
 * - Existing main entry → only `model` changes; `engine`, `parameters` and `cache` are
 *   whatever the config already declared, since those are the fields the service actually
 *   reads off the template (`rails.py:253`).
 * - `name` is blank → the main entry is dropped entirely rather than left as a bare
 *   `{type, engine}`, which would read as "configured" while naming nothing. Task LLMs
 *   survive. An emptied array collapses to `undefined` so the key disappears from the
 *   document instead of persisting `models: []`.
 *
 * `mode: 'chat'` on a newly created entry is not cosmetic: the service warns and force-
 * overrides any other value because IGW only routes chat completions (`rails.py:259`).
 */
export const setMainModelName = (
  models: Model[] | undefined,
  name: string
): Model[] | undefined => {
  const list = models ?? [];
  const index = list.findIndex((model) => model.type === MAIN_MODEL_TYPE);

  if (name.trim() === '') {
    if (index === -1) return models;
    const next = list.filter((_, i) => i !== index);
    return next.length ? next : undefined;
  }
  if (index === -1) {
    return [
      ...list,
      { type: MAIN_MODEL_TYPE, engine: GUARDRAIL_DEFAULT_ENGINE, mode: 'chat', model: name },
    ];
  }
  return list.map((model, i) => (i === index ? { ...model, model: name } : model));
};
