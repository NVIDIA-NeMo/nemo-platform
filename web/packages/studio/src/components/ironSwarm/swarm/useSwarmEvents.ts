// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useIronSwarmGetRunEvents } from '@nemo/sdk/generated/iron-swarm/api';
import type { SwarmEvent } from '@studio/components/ironSwarm/eventTypes';
import { useEffect, useState } from 'react';

const POLL_INTERVAL_MS = 1000;
const MAX_EVENTS = 500;

export const useSwarmEvents = (workspace: string, runName: string): SwarmEvent[] => {
  const [afterId, setAfterId] = useState(0);
  const [allEvents, setAllEvents] = useState<SwarmEvent[]>([]);

  const { data } = useIronSwarmGetRunEvents(workspace, runName, { after: afterId }, {
    query: {
      enabled: Boolean(runName),
      refetchInterval: POLL_INTERVAL_MS,
    },
  });

  useEffect(() => {
    if (!data?.events?.length) return;
    const next: SwarmEvent[] = data.events.map((e) => ({
      id: typeof e['id'] === 'number' ? e['id'] : Date.now(),
      event: typeof e['event'] === 'string' ? e['event'] : '',
      payload: (e['payload'] ?? {}) as Record<string, unknown>,
      ts: Date.now(),
    }));
    setAllEvents((prev) => [...prev, ...next].slice(-MAX_EVENTS));
    setAfterId(next[next.length - 1].id);
  }, [data]);

  useEffect(() => {
    setAllEvents([]);
    setAfterId(0);
  }, [runName]);

  return allEvents;
};
