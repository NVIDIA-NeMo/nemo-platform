// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// The agents service is a separate plugin, so its client is neither on
// `host.sdk` (platform only) nor in this plugin's OpenAPI spec. It is one
// paginated GET, so it goes through this plugin's own fetcher.

import { customFetch } from '@iron-swarm/api/fetcher';

const AGENTS_PAGE_SIZE = 100;

/** Only the field the agent picker renders. */
export interface AgentSummary {
  name?: string;
}

interface AgentsPage {
  data?: AgentSummary[];
  pagination?: { total_pages?: number };
}

export const fetchAgentsForSelect = async (
  workspace: string,
  signal: AbortSignal
): Promise<AgentSummary[]> => {
  const allAgents: AgentSummary[] = [];
  let page = 1;

  while (true) {
    const response = await customFetch<AgentsPage>({
      url: `/apis/agents/v2/workspaces/${encodeURIComponent(workspace)}/agents`,
      method: 'GET',
      params: { page, page_size: AGENTS_PAGE_SIZE, sort: 'name' },
      signal,
    });
    const batch = response.data ?? [];
    allAgents.push(...batch);

    const totalPages = response.pagination?.total_pages;
    if (totalPages ? page >= totalPages : batch.length < AGENTS_PAGE_SIZE) break;
    page += 1;
  }

  return allAgents;
};
