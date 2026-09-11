// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useAgentsListAgents } from '@nemo/sdk/generated/agents/agents';
import { useListTraces } from '@nemo/sdk/generated/platform/traces';
import { useMemo } from 'react';

/** The API's ceiling. Intake exposes no distinct-agent facet, so the names are deduped from a
 *  page of traces; anything older than this many traces is not offered. */
const TRACE_SCAN_PAGE_SIZE = 1000;

export interface TraceAgentNames {
  /** Agent names seen on traces that have no agent entity yet, oldest naming preserved. */
  names: string[];
  /** Names already registered, so the caller can say why the list is short. */
  registeredCount: number;
  isLoading: boolean;
}

/**
 * Agent names observed in ingested traces that are not registered agents yet.
 *
 * `summary` mode is the cheapest response that still carries `agent_name`: it omits payloads and
 * rollups, which this never reads.
 */
export const useTraceAgentNames = (workspace: string, enabled: boolean): TraceAgentNames => {
  const { data: tracesResponse, isLoading: isTracesLoading } = useListTraces(
    workspace,
    { page_size: TRACE_SCAN_PAGE_SIZE, mode: 'summary', sort: '-started_at' },
    { query: { enabled: enabled && !!workspace } }
  );

  const { data: agentsResponse, isLoading: isAgentsLoading } = useAgentsListAgents(
    workspace,
    undefined,
    { query: { enabled: enabled && !!workspace } }
  );

  return useMemo(() => {
    const registered = new Set(
      (agentsResponse?.data ?? []).flatMap((agent) => (agent.name ? [agent.name] : []))
    );
    const seen = new Set<string>();
    for (const trace of tracesResponse?.data ?? []) {
      const name = trace.agent_name?.trim();
      if (name && !registered.has(name)) seen.add(name);
    }
    return {
      names: [...seen].sort((a, b) => a.localeCompare(b)),
      registeredCount: registered.size,
      isLoading: isTracesLoading || isAgentsLoading,
    };
  }, [tracesResponse, agentsResponse, isTracesLoading, isAgentsLoading]);
};
