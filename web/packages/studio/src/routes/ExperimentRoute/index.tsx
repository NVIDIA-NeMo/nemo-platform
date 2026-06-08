// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useListExperimentGroups } from '@nemo/sdk/generated/platform/api';
import type { ExperimentGroupResponse } from '@nemo/sdk/generated/platform/schema';
import {
  PageHeader,
  PaginationArrowButton,
  PaginationControlsGroup,
  PaginationItemRangeText,
  PaginationNavigationGroup,
  PaginationPageCountText,
  PaginationPageInput,
  PaginationPageSizeSelect,
  PaginationRoot,
  Stack,
  StatusMessage,
  Text,
} from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { Loading } from '@studio/components/Layouts/Loading';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { ExperimentGroupCard } from '@studio/routes/ExperimentRoute/ExperimentGroupCard';
import { keepPreviousData } from '@tanstack/react-query';
import { CircleAlert } from 'lucide-react';
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
    <AccessibleTitle title="Experiment groups">
      <Stack className="h-full overflow-auto" gap="density-2xl" padding="density-2xl">
        <PageHeader
          className="p-0"
          slotHeading="Experiment groups"
          slotDescription="Manage groups for online optimization. Review reports down to the frame level."
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
              <div className="mx-auto w-full max-w-[1200px]">
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
              </div>
            )}
          </div>
        )}
      </Stack>
    </AccessibleTitle>
  );
};
