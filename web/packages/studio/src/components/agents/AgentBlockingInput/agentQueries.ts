// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { agentsListAgents } from '@nemo/sdk/generated/agents/api';
import type { Agent } from '@nemo/sdk/generated/agents/schema';

const AGENTS_PAGE_SIZE = 100;

export const fetchAgentsForSelect = async (
  workspace: string,
  signal: AbortSignal
): Promise<Agent[]> => {
  const allAgents: Agent[] = [];
  let page = 1;

  while (true) {
    const response = await agentsListAgents(
      workspace,
      { page, page_size: AGENTS_PAGE_SIZE, sort: 'name' },
      signal
    );
    const batch = response.data ?? [];
    allAgents.push(...batch);

    const totalPages = response.pagination?.total_pages;
    if (totalPages ? page >= totalPages : batch.length < AGENTS_PAGE_SIZE) break;
    page += 1;
  }

  return allAgents;
};
