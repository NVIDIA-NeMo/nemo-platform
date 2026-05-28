// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { KVPair } from '@nemo/common/src/components/KVPair';
import { utcToLocalDate } from '@nemo/common/src/utils/date';
import type { BenchmarksListResponse } from '@nemo/sdk/generated/platform/schema';
import { Block, SidePanel, Stack } from '@nvidia/foundations-react-core';
import { Loading } from '@studio/components/Layouts/Loading';
import type { ComponentProps, FC } from 'react';

type BenchmarkDetail = BenchmarksListResponse['data'][number];

interface BenchmarkDetailsPanelProps {
  benchmark?: BenchmarkDetail;
  /** When true, shows a spinner instead of benchmark fields (e.g. while fetching by URL). */
  isLoading?: boolean;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  attributes?: {
    SidePanel?: ComponentProps<typeof SidePanel>;
  };
}

export const BenchmarkDetailsPanel: FC<BenchmarkDetailsPanelProps> = ({
  benchmark,
  isLoading = false,
  open = true,
  onOpenChange,
  attributes,
}) => {
  const metricsText = (() => {
    if (!benchmark || !('metrics' in benchmark) || !benchmark.metrics?.length) return undefined;
    const { metrics } = benchmark;
    if (typeof metrics[0] === 'string') return metrics.join(', ');
    return metrics
      .map((m) => (m && typeof m === 'object' && 'name' in m ? String(m.name) : ''))
      .filter(Boolean)
      .join(', ');
  })();

  const dataset = (() => {
    if (!benchmark || !('dataset' in benchmark) || benchmark.dataset === undefined) {
      return undefined;
    }
    const { dataset: d } = benchmark;
    if (typeof d === 'string') return d;
    try {
      return JSON.stringify(d);
    } catch {
      return String(d);
    }
  })();

  return (
    <SidePanel
      open={open}
      onOpenChange={onOpenChange}
      slotHeading={benchmark?.name ?? 'Benchmark Details'}
      modal
      bordered
      className="w-[440px] [&_.nv-side-panel-main]:p-0"
      {...attributes?.SidePanel}
    >
      <Stack className="overflow-auto">
        <Block padding="4" className={isLoading ? 'min-h-[200px]' : undefined}>
          {isLoading ? (
            <Loading description="Loading benchmark..." />
          ) : (
            <Stack gap="2">
              <KVPair label="Name" value={benchmark?.name} />
              {benchmark?.workspace && <KVPair label="Workspace" value={benchmark.workspace} />}
              {benchmark?.project && <KVPair label="Project" value={benchmark.project} />}
              {benchmark?.description && (
                <KVPair label="Description" value={benchmark.description} />
              )}
              {metricsText && <KVPair label="Metrics" value={metricsText} />}
              {dataset && <KVPair label="Dataset" value={dataset} />}
              <KVPair
                label="Created"
                value={utcToLocalDate(benchmark?.created_at)?.toLocaleString()}
              />
              <KVPair
                label="Updated"
                value={utcToLocalDate(benchmark?.updated_at)?.toLocaleString()}
              />
            </Stack>
          )}
        </Block>
      </Stack>
    </SidePanel>
  );
};
