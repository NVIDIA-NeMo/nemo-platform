// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useRelativeTimeSince } from '@nemo/common/src/components/RelativeTime';
import { useListExperimentGroups, useListExperiments } from '@nemo/sdk/generated/platform/api';
import type { ExperimentGroupResponse } from '@nemo/sdk/generated/platform/schema';
import {
  Divider,
  PageHeader,
  PaginationArrowButton,
  PaginationControlsGroup,
  PaginationItemRangeText,
  PaginationNavigationGroup,
  PaginationPageCountText,
  PaginationPageInput,
  PaginationPageSizeSelect,
  PaginationRoot,
  Skeleton,
  Stack,
  StatusMessage,
  Tag,
  Text,
} from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { Loading } from '@studio/components/Layouts/Loading';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { Metric } from '@studio/routes/ExperimentRoute/Metric';
import { keepPreviousData } from '@tanstack/react-query';
import { CircleAlert, MessageSquareText } from 'lucide-react';
import { type FC, useState } from 'react';

const DEFAULT_PAGE_SIZE = 5;

export const ExperimentRoute: FC = () => {
  useBreadcrumbs({ items: [{ slotLabel: 'Experiments' }] });

  const workspace = useWorkspaceFromPath();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);

  const { data, isLoading, error } = useListExperimentGroups(
    workspace,
    { page, page_size: pageSize },
    { query: { placeholderData: keepPreviousData } }
  );

  if (isLoading) {
    return <Loading description="Loading experiments..." />;
  }

  if (error) {
    return (
      <StatusMessage
        className="mx-auto mt-density-2xl"
        size="medium"
        slotMedia={<CircleAlert width={65} height={65} />}
        slotHeading="Error loading experiments"
        slotSubheading={error.message}
      />
    );
  }

  const groups = data?.data ?? [];
  const totalResults = data?.pagination?.total_results ?? 0;

  return (
    <AccessibleTitle title="Experiments">
      <Stack className="h-full overflow-auto" gap="density-2xl" padding="density-2xl">
        <PageHeader
          className="p-0"
          slotHeading="Experiments"
          slotDescription="Result ledger for offline optimization. Review results down to the trace level."
        />
        {groups.length === 0 ? (
          <Text kind="body/regular/md" className="text-secondary">
            No experiment groups yet.
          </Text>
        ) : (
          <div className="flex flex-col flex-1 min-w-0 min-h-0">
            <div className="flex-1 overflow-auto">
              <Stack gap="density-md">
                {groups.map((group: ExperimentGroupResponse) => (
                  <ExperimentGroupCard key={group.id} group={group} workspace={workspace} />
                ))}
              </Stack>
            </div>
            {totalResults > 0 && (
              <PaginationRoot
                totalItems={totalResults}
                page={page}
                pageSize={pageSize}
                pageSizeOptions={[5, 10, 20, 50]}
                onPageChange={setPage}
                onPageSizeChange={(size) => {
                  setPageSize(size);
                  setPage(1);
                }}
              >
                <PaginationControlsGroup>
                  <Text>Items per page</Text>
                  <PaginationPageSizeSelect />
                  <PaginationItemRangeText />
                </PaginationControlsGroup>
                <PaginationNavigationGroup className="gap-2">
                  <PaginationArrowButton direction="first" />
                  <PaginationArrowButton direction="previous" />
                  <PaginationPageInput />
                  <PaginationPageCountText
                    pageCountTextFormatFn={(pageMeta) => `of ${pageMeta.total}`}
                  />
                  <PaginationArrowButton direction="next" />
                  <PaginationArrowButton direction="last" />
                </PaginationNavigationGroup>
              </PaginationRoot>
            )}
          </div>
        )}
      </Stack>
    </AccessibleTitle>
  );
};

interface UpdatedAtProps {
  datetime: string;
}

const UpdatedAt: FC<UpdatedAtProps> = ({ datetime }) => {
  const relative = useRelativeTimeSince(datetime);
  return (
    <Text kind="label/regular/xs" className="text-tertiary">
      Updated {relative}
    </Text>
  );
};

interface ExperimentGroupCardProps {
  group: ExperimentGroupResponse;
  workspace: string;
}

const ExperimentGroupCard: FC<ExperimentGroupCardProps> = ({ group, workspace }) => {
  const { data: experimentsData } = useListExperiments(workspace, {
    filter: { experiment_group_id: group.id },
    page_size: 100,
  });

  const experiments = experimentsData?.data ?? [];
  const experimentCount = experimentsData?.pagination?.total_results ?? experiments.length;

  // Collect evaluator names and average their means across experiments in this group
  const evaluatorNames = [
    ...new Set(experiments.flatMap((e) => Object.keys(e.aggregate_scores ?? {}))),
  ];
  const scoreEntries = evaluatorNames
    .map((name) => {
      const means = experiments
        .map((e) => e.aggregate_scores?.[name]?.mean)
        .filter((v): v is number => v !== undefined && v !== null);
      const avg = means.length > 0 ? means.reduce((a, b) => a + b, 0) / means.length : null;
      return { name, avg };
    })
    .filter((entry): entry is { name: string; avg: number } => entry.avg !== null);

  return (
    <div className="flex items-center gap-6 rounded bg-surface py-[18px]">
      {/* Slot 1: Status — no backend field yet, skeleton holds the space */}
      <Skeleton className="h-6 w-20 shrink-0" />

      {/* Slot 2: Main info */}
      <div className="flex flex-col items-start gap-[7px] flex-1">
        <Text kind="title/sm">{group.name}</Text>
        {group.description && (
          <Text kind="body/regular/sm" className="text-secondary">
            {group.description}
          </Text>
        )}
        <div className="flex items-center gap-4">
          <Tag kind="outline" color="gray" readOnly>
            {experimentCount} Experiments
          </Tag>
          {/* UserPill: no author field on ExperimentGroupResponse yet */}
          <Skeleton className="h-6 w-24 rounded-full" />
          {group.updated_at && <UpdatedAt datetime={group.updated_at} />}
        </div>
      </div>

      {/* Slot 3: Stats */}
      <div className="flex shrink-0 items-center gap-6">
        {/* Variable evaluator score metrics */}
        {scoreEntries.map(({ name, avg }) => (
          <Metric key={name} title={name} value={`${(avg * 100).toFixed(1)}%`} />
        ))}

        {/* Pipe — only shown when there are scores to separate */}
        {scoreEntries.length > 0 && <Divider orientation="vertical" />}

        <Metric title="Experiments" value={String(experimentCount)} />
        <Metric title="Feedback" icon={<MessageSquareText />} value="—" />
      </div>
    </div>
  );
};
