// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { LogViewer } from '@nemo/common/src/components/LogViewer';
import {
  getAgentsStreamDeploymentLogsQueryKey,
  useAgentsGetDeploymentLogs,
} from '@nemo/sdk/generated/agents/api';
import type { AgentDeployment } from '@nemo/sdk/generated/agents/schema';
import type { PlatformJobLog } from '@nemo/sdk/generated/platform/schema';
import { Block, Select, Stack, Text } from '@nvidia/foundations-react-core';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { logger } from '@studio/util/logger';
import { streamSse } from '@studio/util/sseStream';
import { type FC, useEffect, useMemo, useState } from 'react';
import { useAuth } from 'react-oidc-context';

interface DeploymentLogsViewProps {
  workspace: string;
  /** All known deployments for the active agent — any status. */
  deployments: AgentDeployment[];
  /** Controlled selection — when provided, the picker reflects this deployment. */
  selectedDeploymentName?: string;
  /** Called when the user (or a caller) changes the selected deployment. */
  onSelectDeployment?: (name: string) => void;
}

export const DeploymentLogsView: FC<DeploymentLogsViewProps> = ({
  workspace,
  deployments,
  selectedDeploymentName,
  onSelectDeployment,
}) => {
  const sortedDeployments = useMemo(
    () =>
      [...deployments].sort((a, b) => {
        const aCreated = a.created_at ?? '';
        const bCreated = b.created_at ?? '';
        return bCreated.localeCompare(aCreated);
      }),
    [deployments]
  );
  const [internalName, setInternalName] = useState<string | undefined>(
    () => selectedDeploymentName ?? sortedDeployments[0]?.name
  );
  const isControlled = selectedDeploymentName !== undefined;
  const selectedName = isControlled ? selectedDeploymentName : internalName;
  const setSelectedName = (name: string) => {
    if (!isControlled) setInternalName(name);
    onSelectDeployment?.(name);
  };

  useEffect(() => {
    if (isControlled) return;
    if (!internalName) {
      setInternalName(sortedDeployments[0]?.name);
      return;
    }
    const stillPresent = sortedDeployments.some((d) => d.name === internalName);
    if (!stillPresent) setInternalName(sortedDeployments[0]?.name);
  }, [sortedDeployments, internalName, isControlled]);

  if (sortedDeployments.length === 0) {
    return (
      <Stack gap="density-md" padding="density-md">
        <Text kind="body/regular/sm" className="text-subtle">
          No deployments yet for this agent. Deploy first to capture logs.
        </Text>
      </Stack>
    );
  }
  const pOffset = '2';

  return (
    <Stack className="h-full min-h-0" gap="2">
      {sortedDeployments.length > 1 && (
        <Block className="shrink-0" paddingX={pOffset}>
          <Select
            value={selectedName ?? ''}
            items={sortedDeployments.flatMap((d) =>
              d.name
                ? [
                    {
                      value: d.name,
                      children: d.status ? `${d.name} · ${d.status}` : d.name,
                    },
                  ]
                : []
            )}
            onValueChange={(v) => setSelectedName(v)}
          />
        </Block>
      )}
      <Block className="flex-1 min-h-0 overflow-auto" paddingX={pOffset}>
        {selectedName ? (
          <LogsForDeployment workspace={workspace} deploymentName={selectedName} />
        ) : null}
      </Block>
    </Stack>
  );
};

interface LogsForDeploymentProps {
  workspace: string;
  deploymentName: string;
}

const TAIL_LINES = 500;
// Cap the live buffer so a long-lived, noisy stream can't grow state unbounded.
const MAX_STREAMED_LINES = 5000;

const LogsForDeployment: FC<LogsForDeploymentProps> = ({ workspace, deploymentName }) => {
  const { data, isLoading } = useAgentsGetDeploymentLogs(
    workspace,
    deploymentName,
    { tail: TAIL_LINES },
    // Short staleTime: the live SSE stream keeps logs current after mount, so we
    // only need a fresh tail baseline, not a refetch on every quick tab toggle.
    { query: { staleTime: 5000 } }
  );

  const [streamedLines, setStreamedLines] = useState<PlatformJobLog[]>([]);
  // Reset on deployment change so we don't stitch one process's tail onto another.
  useEffect(() => {
    setStreamedLines([]);
  }, [deploymentName]);

  const accessToken = useAuth()?.user?.access_token;
  // Byte offset just past the tail; resume the stream from here so lines written
  // between the tail fetch and the stream opening aren't dropped.
  const tailOffset = data?.next_offset;

  useEffect(() => {
    // Wait for the tail query to settle so the stream can resume from tailOffset.
    if (!deploymentName || isLoading) return;
    const url = `${PLATFORM_BASE_URL}${getAgentsStreamDeploymentLogsQueryKey(workspace, deploymentName)[0]}`;
    const controller = new AbortController();
    void streamSse(url, {
      signal: controller.signal,
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : undefined,
      initialLastEventId: tailOffset != null ? String(tailOffset) : undefined,
      onEvent: (event) => {
        try {
          const parsed = JSON.parse(event.data) as PlatformJobLog;
          setStreamedLines((prev) => {
            const next = [...prev, parsed];
            return next.length > MAX_STREAMED_LINES
              ? next.slice(next.length - MAX_STREAMED_LINES)
              : next;
          });
        } catch {
          // ignore malformed lines
        }
      },
      onError: (err) => {
        logger.warn(`Log stream interrupted for deployment ${deploymentName}; retrying`, err);
      },
    });
    return () => controller.abort();
  }, [workspace, deploymentName, accessToken, isLoading, tailOffset]);

  const logs = useMemo<PlatformJobLog[]>(() => {
    const initial = (data?.data ?? []).map(
      (line): PlatformJobLog => ({
        timestamp: line.timestamp,
        message: line.message,
        job: '',
        job_step: '',
        job_task: '',
      })
    );
    return [...initial, ...streamedLines];
  }, [data, streamedLines]);

  return (
    <LogViewer
      logs={logs}
      isLoading={isLoading && logs.length === 0}
      downloadFilename={`${deploymentName}.log`}
      rows={40}
      emptyMessage="No log output yet — the deployment may not have started writing."
    />
  );
};
