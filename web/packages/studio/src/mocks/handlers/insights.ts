// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { InsightListItem } from '@studio/api/optimizer';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { http, HttpResponse } from 'msw';

/**
 * Insights plugin routes. They are not in the generated SDK, so both the client
 * (`@studio/api/optimizer`) and these handlers are hand-written against the plugin's
 * `/apis/insights/v2/workspaces/{workspace}/insights` contract.
 */
const INSIGHTS_URL = `${PLATFORM_BASE_URL}/apis/insights/v2/workspaces/:workspace/insights`;

export const mockInsights: InsightListItem[] = [
  {
    id: 'ins-1',
    name: 'ambiguous-system-prompt',
    title: 'Ambiguous system prompt causes tool misfires',
    description:
      'The system prompt does not say which tool owns order lookups, so the agent calls the search tool for questions the orders tool answers.',
    agent: 'react-agent',
    status: 'open',
    trace_refs: Array.from({ length: 12 }, (_, index) => `trace-a-${index}`),
    experiment_group_count: 1,
    last_seen_at: '2026-08-14T09:00:00Z',
    created_at: '2026-08-10T09:00:00Z',
    updated_at: '2026-08-14T09:00:00Z',
  },
  {
    id: 'ins-2',
    name: 'latency-long-context',
    title: 'Latency spikes on long context (>8k tokens)',
    description:
      'Sessions whose accumulated context passes ~8k tokens take more than three times as long to return.',
    agent: 'react-agent',
    status: 'open',
    trace_refs: Array.from({ length: 5 }, (_, index) => `trace-b-${index}`),
    experiment_group_count: 0,
    last_seen_at: '2026-08-12T09:00:00Z',
    created_at: '2026-08-11T09:00:00Z',
    updated_at: '2026-08-12T09:00:00Z',
  },
];

export const insightsHandlers = [
  http.get(INSIGHTS_URL, ({ request }) => {
    const params = new URL(request.url).searchParams;
    const agent = params.get('agent');
    const status = params.get('status');

    const matches = mockInsights.filter(
      (insight) => (!agent || insight.agent === agent) && (!status || insight.status === status)
    );

    const page = Number(params.get('page') ?? 1);
    const pageSize = Number(params.get('page_size') ?? 20);
    const data = matches.slice((page - 1) * pageSize, page * pageSize);

    return HttpResponse.json({
      data,
      pagination: {
        page,
        page_size: pageSize,
        current_page_size: data.length,
        total_pages: Math.ceil(matches.length / pageSize),
        total_results: matches.length,
      },
    });
  }),
];
