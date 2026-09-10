// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { OptimizeJob } from '@nemo/sdk/generated/agents/schema';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { http, HttpResponse } from 'msw';

const OPTIMIZE_JOBS_URL = `${PLATFORM_BASE_URL}/apis/agents/v2/workspaces/:workspace/jobs/optimize`;

/**
 * Two studies for `react-agent` and one for another agent, so a test can prove the request scopes
 * the list to one agent — the handler below filters exactly as the server does.
 */
export const mockOptimizeJobs: OptimizeJob[] = [
  {
    id: 'opt-8f21',
    name: 'brevity-sweep-3',
    workspace: 'default',
    status: 'completed',
    created_at: '2026-08-14T09:00:00Z',
    updated_at: '2026-08-14T11:00:00Z',
    spec: { optimize_config: 'optimize-brevity.yaml', agent: 'react-agent' },
  },
  {
    id: 'opt-9a03',
    name: 'accuracy-sweep-1',
    workspace: 'default',
    status: 'active',
    created_at: '2026-08-13T09:00:00Z',
    updated_at: '2026-08-13T09:30:00Z',
    // Workspace-qualified reference for the same agent — must still match.
    spec: { optimize_config: 'optimize-accuracy.yaml', agent: 'default/react-agent' },
  },
  {
    id: 'opt-4400',
    name: 'other-agent-sweep',
    workspace: 'default',
    status: 'error',
    created_at: '2026-08-12T09:00:00Z',
    spec: { optimize_config: 'optimize-other.yaml', agent: 'other-agent' },
  },
];

interface FilterQuery {
  'spec.agent'?: { $in?: string[] };
  name?: { $like?: string };
}

/**
 * The slice of the platform filter syntax this endpoint is called with: exact `$in` on the dotted
 * spec path, case-insensitive substring `$like` on the name. Modelled here rather than ignored so
 * a malformed filter (nested `spec` object, missing operator) fails the test instead of passing.
 */
const applyFilter = (jobs: OptimizeJob[], raw: string | null): OptimizeJob[] => {
  if (!raw) return jobs;
  const filter = JSON.parse(raw) as FilterQuery;
  const agents = filter['spec.agent']?.$in;
  const like = filter.name?.$like?.toLowerCase();
  return jobs.filter((job) => {
    if (agents && !agents.includes(String(job.spec?.agent ?? ''))) return false;
    return !like || job.name.toLowerCase().includes(like);
  });
};

export const agentOptimizeJobsHandlers = [
  http.get(OPTIMIZE_JOBS_URL, ({ request }) => {
    const url = new URL(request.url);
    const page = Number(url.searchParams.get('page') ?? 1);
    const pageSize = Number(url.searchParams.get('page_size') ?? 50);
    const matches = applyFilter(mockOptimizeJobs, url.searchParams.get('filter'));
    const data = matches.slice((page - 1) * pageSize, page * pageSize);
    return HttpResponse.json({
      data,
      pagination: {
        page,
        page_size: pageSize,
        current_page_size: data.length,
        total_pages: Math.max(1, Math.ceil(matches.length / pageSize)),
        total_results: matches.length,
      },
    });
  }),
];
