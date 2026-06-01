// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DateRangeFilterField } from '@nemo/common/src/components/FilterFields';
import { PlatformJobStatus } from '@nemo/sdk/generated/platform/schema';
import { Accordion, Checkbox, Flex, Stack } from '@nvidia/foundations-react-core';
import type { EvaluationResultsFilterState } from '@studio/routes/evaluation/EvaluationResultsRoute/types';
import { type Dispatch, type SetStateAction } from 'react';

const STATUS_OPTIONS = Object.values(PlatformJobStatus).map((status) => ({
  label: status.charAt(0).toUpperCase() + status.slice(1),
  value: status,
}));

export const FilterPanel = ({
  filterState,
  setFilterState,
}: {
  filterState: EvaluationResultsFilterState;
  setFilterState: Dispatch<SetStateAction<EvaluationResultsFilterState>>;
}) => {
  const selectedStatuses = filterState?.filter?.status ?? [];

  const handleStatusChange = (status: PlatformJobStatus, checked: boolean) => {
    setFilterState((prev) => {
      const current = prev?.filter?.status ?? [];
      const updated = checked ? [...current, status] : current.filter((s) => s !== status);
      return {
        ...prev,
        filter: {
          ...prev.filter,
          status: updated.length > 0 ? updated : undefined,
        },
      };
    });
  };

  return (
    <Accordion
      defaultValue={['status', 'created_at']}
      multiple
      items={[
        {
          slotTrigger: (
            <Flex align="center" gap="2">
              Status
            </Flex>
          ),
          slotContent: (
            <Stack gap="density-md">
              {STATUS_OPTIONS.map(({ label, value }) => (
                <Checkbox
                  key={value}
                  attributes={{
                    CheckboxInput: {
                      id: `eval-result-status-${value}`,
                      'aria-label': label,
                    },
                    Label: { htmlFor: `eval-result-status-${value}` },
                  }}
                  checked={selectedStatuses.includes(value)}
                  slotLabel={label}
                  onCheckedChange={(checked) => handleStatusChange(value, !!checked)}
                />
              ))}
            </Stack>
          ),
          value: 'status',
        },
        {
          slotTrigger: (
            <Flex align="center" gap="2">
              Created
            </Flex>
          ),
          slotContent: (
            <DateRangeFilterField
              dataTestId="evaluation-result-created-at-filter"
              value={filterState?.filter?.created_at}
              onValueChange={(value) => {
                setFilterState((prev) => ({
                  ...prev,
                  filter: { ...prev.filter, created_at: value },
                }));
              }}
            />
          ),
          value: 'created_at',
        },
      ]}
    />
  );
};
