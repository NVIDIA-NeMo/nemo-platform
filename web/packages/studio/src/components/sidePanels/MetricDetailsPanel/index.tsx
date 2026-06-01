// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { KVPair } from '@nemo/common/src/components/KVPair';
import { utcToLocalDate } from '@nemo/common/src/utils/date';
import type {
  MetricsListResponse,
  RangeScore,
  RubricScore,
} from '@nemo/sdk/generated/platform/schema';
import { Accordion, Block, SidePanel, Stack, Table, Text } from '@nvidia/foundations-react-core';
import type { ComponentProps, FC } from 'react';

type MetricItem = MetricsListResponse['data'][number];

interface MetricDetailsPanelProps {
  metric?: MetricItem;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  attributes?: {
    SidePanel?: ComponentProps<typeof SidePanel>;
  };
}

export const MetricDetailsPanel: FC<MetricDetailsPanelProps> = ({
  metric,
  open = true,
  onOpenChange,
  attributes,
}) => {
  const supportedJobTypes =
    'supported_job_types' in (metric ?? {}) && Array.isArray(metric?.supported_job_types)
      ? metric.supported_job_types.join(', ')
      : undefined;

  const description =
    'description' in (metric ?? {}) ? (metric as { description?: string }).description : undefined;

  const scores =
    metric && 'scores' in metric && Array.isArray(metric.scores)
      ? (metric.scores as (RubricScore | RangeScore)[])
      : [];

  return (
    <SidePanel
      open={open}
      onOpenChange={onOpenChange}
      slotHeading={metric?.name ?? 'Metric Details'}
      modal
      bordered
      className="w-[440px] [&_.nv-side-panel-main]:p-0"
      {...attributes?.SidePanel}
    >
      <Stack className="overflow-auto">
        <Block padding="4">
          <Stack gap="4">
            <KVPair label="Name" value={metric?.name} />
            {metric?.type && <KVPair label="Type" value={metric.type} />}
            {description && <KVPair label="Description" value={description} />}
            <KVPair label="Created" value={utcToLocalDate(metric?.created_at)?.toLocaleString()} />
            <KVPair label="Updated" value={utcToLocalDate(metric?.updated_at)?.toLocaleString()} />
            {supportedJobTypes && <KVPair label="Supported Job Types" value={supportedJobTypes} />}
          </Stack>
        </Block>
        {scores.length > 0 && (
          <>
            <Block padding="4" className="pb-2">
              <Text kind="label/semibold/lg">Score Definitions</Text>
            </Block>
            <Accordion
              multiple
              className="w-full border-t border-base"
              defaultValue={scores.map((s) => s.name)}
              items={scores.map((score) => ({
                chevronPosition: 'start' as const,
                value: score.name,
                slotTrigger: score.name,
                slotContent: (
                  <Stack gap="2">
                    {score.description && (
                      <Text kind="body/regular/md" className="text-secondary">
                        {score.description}
                      </Text>
                    )}
                    {'rubric' in score ? (
                      <Table
                        className="w-full"
                        layout="fixed"
                        align="left"
                        columns={[
                          {
                            children: 'Label',
                            attributes: { TableHeaderCell: { style: { width: '100px' } } },
                          },
                          { children: 'Description' },
                          {
                            children: 'Value',
                            attributes: { TableHeaderCell: { style: { width: '60px' } } },
                          },
                        ]}
                        rows={score.rubric.map((entry) => ({
                          cells: [
                            { children: entry.label },
                            { children: entry.description ?? '-' },
                            { children: entry.value },
                          ],
                        }))}
                      />
                    ) : (
                      <KVPair label="Range" value={`${score.minimum} – ${score.maximum}`} />
                    )}
                  </Stack>
                ),
              }))}
            />
          </>
        )}
      </Stack>
    </SidePanel>
  );
};
