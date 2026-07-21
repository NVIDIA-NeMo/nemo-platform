// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { getIronSwarmGetRunEventsQueryKey } from '@nemo/sdk/generated/iron-swarm/api';
import type { SwarmEvent } from '@studio/components/ironSwarm/eventTypes';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { logger } from '@studio/util/logger';
import { streamSse } from '@studio/util/sseStream';
import { useEffect, useState } from 'react';
import { useAuth } from 'react-oidc-context';

const MAX_EVENTS = 500;

// One SSE subscription to a run's live EventBus, relayed by the plugin. Both the swarm graph and the
// message feed read this single ordered stream (Last-Event-ID resume is handled by streamSse).
export const useSwarmEvents = (workspace: string, runName: string): SwarmEvent[] => {
  const accessToken = useAuth()?.user?.access_token;
  const [events, setEvents] = useState<SwarmEvent[]>([]);

  useEffect(() => {
    if (!runName) return undefined;
    setEvents([]);
    const url = `${PLATFORM_BASE_URL}${getIronSwarmGetRunEventsQueryKey(workspace, runName)[0]}`;
    const controller = new AbortController();
    void streamSse(url, {
      signal: controller.signal,
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : undefined,
      onEvent: (evt) => {
        try {
          const parsed = JSON.parse(evt.data) as {
            event: string;
            payload: Record<string, unknown>;
          };
          const next: SwarmEvent = {
            id: evt.id ? Number(evt.id) : Date.now(),
            event: parsed.event,
            payload: parsed.payload ?? {},
            ts: Date.now(),
          };
          setEvents((prev) => {
            const appended = [...prev, next];
            return appended.length > MAX_EVENTS
              ? appended.slice(appended.length - MAX_EVENTS)
              : appended;
          });
        } catch {
          // ignore malformed frames
        }
      },
      onError: (err) =>
        logger.warn(`Iron Swarm event stream interrupted for ${runName}; retrying`, err),
    });
    return () => controller.abort();
  }, [workspace, runName, accessToken]);

  return events;
};
