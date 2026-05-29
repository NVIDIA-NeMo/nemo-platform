// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ModelWorkspaceGroup } from '@nemo/common/src/api/models/useModels';
import type { ModelEntity } from '@nemo/sdk/generated/platform/schema';
import { useMemo } from 'react';

const FT_NAMESPACE = 'fine-tuned-mock';

/** Three mock fine-tuned entries so the Fine-tuned section is always present
 *  for design review, even when the workspace doesn't have a Customizer job
 *  yet. Each is shaped like a real ModelEntity so ModelSelectV2 renders it
 *  exactly the same as a real one. */
const MOCK_FT_MODELS: ModelEntity[] = [
  {
    id: 'mock-ft-1',
    name: 'llama-3.1-70b-instruct-ft-support',
    workspace: FT_NAMESPACE,
    description: 'Mock: support-triage fine-tune (from llama-3.1-70b-instruct)',
    created_at: '2026-01-01T00:00:00.000Z',
    updated_at: '2026-01-01T00:00:00.000Z',
    trust_remote_code: false,
    backend_format: 'OPENAI_CHAT',
    adapters: [],
    custom_fields: {},
    model_providers: [],
  } as unknown as ModelEntity,
  {
    id: 'mock-ft-2',
    name: 'nemotron-4-340b-rag-tuned',
    workspace: FT_NAMESPACE,
    description: 'Mock: RAG-tuned Nemotron-4 340B',
    created_at: '2026-01-01T00:00:00.000Z',
    updated_at: '2026-01-01T00:00:00.000Z',
    trust_remote_code: false,
    backend_format: 'OPENAI_CHAT',
    adapters: [],
    custom_fields: {},
    model_providers: [],
  } as unknown as ModelEntity,
  {
    id: 'mock-ft-3',
    name: 'mixtral-8x22b-finetuned-claims',
    workspace: FT_NAMESPACE,
    description: 'Mock: claims-processing fine-tune on Mixtral 8x22B',
    created_at: '2026-01-01T00:00:00.000Z',
    updated_at: '2026-01-01T00:00:00.000Z',
    trust_remote_code: false,
    backend_format: 'OPENAI_CHAT',
    adapters: [],
    custom_fields: {},
    model_providers: [],
  } as unknown as ModelEntity,
];

const FT_PATTERN = /(-|_)(ft|finetuned|tuned)(-|_|$)/i;

/**
 * Returns a single Fine-tuned group containing:
 * - Real models in the workspace whose URN matches the fine-tune heuristic
 *   (-ft-, -finetuned, -tuned suffixes / segments).
 * - A fixed set of mock fine-tuned entries so the section is always visible
 *   for design review.
 *
 * The returned array is meant to be concatenated to the workspace groups
 * passed into ModelSelectV2.
 */
export function useFineTunedGroup(models: ModelEntity[]): ModelWorkspaceGroup[] {
  return useMemo(() => {
    const realFt = models.filter((m) => !!m?.name && FT_PATTERN.test(m.name));
    const allFt = [...realFt, ...MOCK_FT_MODELS];
    if (allFt.length === 0) return [];
    return [
      {
        workspace: 'Fine-tuned',
        models: allFt,
      },
    ];
  }, [models]);
}
