// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { GuardrailConfig } from '@nemo/sdk/generated/platform/schema';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { http, HttpResponse } from 'msw';

export const mockGuardrailConfigs: GuardrailConfig[] = [
  {
    id: 'cfg-1',
    entity_id: 'cfg-1',
    parent: 'ws-default',
    name: 'pii-filter',
    workspace: 'default',
    description: 'Blocks PII in user inputs and outputs',
    created_at: '2026-04-12T10:00:00.000Z',
    created_by: 'user@example.com',
    updated_at: '2026-04-12T10:00:00.000Z',
    updated_by: 'user@example.com',
    data: {
      models: [
        { type: 'main', engine: 'openai', model: 'gpt-4' },
        { type: 'embeddings', engine: 'openai', model: 'text-embedding-ada-002' },
      ],
      rails: {
        input: { flows: ['check pii', 'check toxicity'] },
        output: { flows: ['mask pii output', 'check output facts'] },
      },
    },
  },
  {
    id: 'cfg-2',
    entity_id: 'cfg-2',
    parent: 'ws-default',
    name: 'toxicity-guard',
    workspace: 'default',
    description: 'Detects and blocks toxic language',
    created_at: '2026-04-11T10:00:00.000Z',
    created_by: 'user@example.com',
    updated_at: '2026-04-11T10:00:00.000Z',
    updated_by: 'user@example.com',
    data: {
      models: [{ type: 'main', engine: 'openai', model: 'gpt-4' }],
      rails: {
        input: { flows: ['check toxicity'] },
        output: { flows: ['filter toxic output'] },
      },
    },
  },
];

export const guardrailsHandlers = [
  http.get(`${PLATFORM_BASE_URL}/apis/guardrails/v2/workspaces/:workspace/configs`, () =>
    HttpResponse.json({
      data: mockGuardrailConfigs,
      pagination: {
        page: 1,
        page_size: 25,
        current_page_size: mockGuardrailConfigs.length,
        total_pages: 1,
        total_results: mockGuardrailConfigs.length,
      },
    })
  ),
  http.get(
    `${PLATFORM_BASE_URL}/apis/guardrails/v2/workspaces/:workspace/configs/:name`,
    ({ params }) => {
      const config = mockGuardrailConfigs.find((c) => c.name === params.name);
      if (!config) return new HttpResponse(null, { status: 404 });
      return HttpResponse.json(config);
    }
  ),
  http.delete(
    `${PLATFORM_BASE_URL}/apis/guardrails/v2/workspaces/:workspace/configs/:name`,
    () => new HttpResponse(null, { status: 200 })
  ),
];
