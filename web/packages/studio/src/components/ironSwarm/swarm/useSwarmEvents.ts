// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useIronSwarmGetEvents } from '@nemo/sdk/generated/iron-swarm/api';
import type { SwarmEvent } from '@studio/components/ironSwarm/eventTypes';
import { useEffect, useState } from 'react';

const POLL_INTERVAL_MS = 1000;

/**
 * Accumulate a run's event stream by polling.
 *
 * The full prefix is kept deliberately: `deriveSwarmState` folds from the first event (all nodes
 * `pending`) and relies on seeing every `phase_started`/`round_started`, so dropping the oldest events
 * would silently corrupt phase and round on long runs — exactly the determinism the fold promises.
 *
 * Pass *isTerminal* once the run can emit nothing further, so polling stops; without it the hook polls
 * for as long as the tab stays open. The trailing fetch still lands: the last batch advances `afterId`,
 * which changes the query key and triggers one final request before the interval goes idle.
 */
export const useSwarmEvents = (
  workspace: string,
  runName: string,
  isTerminal = false
): SwarmEvent[] => {
  const [afterId, setAfterId] = useState(0);
  const [allEvents, setAllEvents] = useState<SwarmEvent[]>([]);

  const { data } = useIronSwarmGetEvents(
    workspace,
    runName,
    { after: afterId },
    {
      query: {
        enabled: Boolean(runName),
        refetchInterval: isTerminal ? false : POLL_INTERVAL_MS,
      },
    }
  );

  useEffect(() => {
    if (!data?.events?.length) return;
    const next: SwarmEvent[] = data.events.map((e: Record<string, unknown>) => ({
      id: typeof e['id'] === 'number' ? e['id'] : Date.now(),
      event: typeof e['event'] === 'string' ? e['event'] : '',
      payload: (e['payload'] ?? {}) as Record<string, unknown>,
      ts: Date.now(),
    }));
    setAllEvents((prev) => [...prev, ...next]);
    setAfterId(next[next.length - 1].id);
  }, [data]);

  useEffect(() => {
    setAllEvents([]);
    setAfterId(0);
  }, [workspace, runName]);

  return allEvents;
};
