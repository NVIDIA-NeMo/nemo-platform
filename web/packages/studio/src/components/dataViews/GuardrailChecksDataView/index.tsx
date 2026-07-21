// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { StudioDataView } from '@nemo/common/src/components/DataView/StudioDataView';
import { LoadingButton } from '@nemo/common/src/components/LoadingButton';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { Badge, Text } from '@nvidia/foundations-react-core';
import { getErrorMessage } from '@studio/api/common/utils';
import {
  useGuardrailChecksForConfig,
  useRunGuardrailCheck,
} from '@studio/api/guardrail-checks/hooks';
import type { GuardrailCheckEntity } from '@studio/api/guardrail-checks/types';
import {
  getCheckInputText,
  getCheckOutputText,
} from '@studio/components/dataViews/GuardrailChecksDataView/checkMessages';
import { getLatestRunStatus } from '@studio/components/dataViews/GuardrailChecksDataView/checkStatus';
import { ErrorPanel } from '@studio/components/ErrorPanel';
import { getGuardrailCheckRoute } from '@studio/routes/utils';
import { keepPreviousData } from '@tanstack/react-query';
import { ListChecks } from 'lucide-react';
import { type ComponentProps, type FC, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';

export interface GuardrailChecksDataViewProps {
  workspace: string;
  configId: string;
  /** Config entity `name` (URL segment) — needed to build the check detail route. */
  configName: string;
}

export const GuardrailChecksDataView: FC<GuardrailChecksDataViewProps> = ({
  workspace,
  configId,
  configName,
}) => {
  const toast = useToast();
  const navigate = useNavigate();
  const runMutation = useRunGuardrailCheck({
    onSuccess: (result) => {
      toast.success(`Ran "${result.entity.name}" — status: ${result.run.status}`);
    },
    onError: (error) => {
      toast.error(getErrorMessage(error, 'Failed to run check'));
    },
  });

  const dataViewState = useStudioDataViewState({
    defaultSort: [{ id: 'updated_at', desc: true }],
  });

  const sortState = dataViewState.sorting.state[0];
  const sortParam = sortState ? `${sortState.desc ? '-' : ''}${sortState.id}` : '-updated_at';

  const { data, isFetching, error } = useGuardrailChecksForConfig(
    workspace,
    configId,
    {
      page: dataViewState.pagination.state.pageIndex + 1,
      page_size: dataViewState.pagination.state.pageSize,
      sort: sortParam,
    },
    { placeholderData: keepPreviousData, enabled: Boolean(configId) }
  );

  const pagination = data?.pagination;

  const makeColumns: ComponentProps<typeof StudioDataView<GuardrailCheckEntity>>['makeColumns'] =
    useCallback(
      ({ accessor }) => [
        accessor('data', {
          id: 'input',
          header: 'Input',
          enableSorting: false,
          cell({ row }) {
            const text = getCheckInputText(row.original.data.messages);
            return (
              <Text className="truncate" title={text}>
                {text || '—'}
              </Text>
            );
          },
        }),
        accessor('data', {
          id: 'output',
          header: 'Output',
          enableSorting: false,
          cell({ row }) {
            const text = getCheckOutputText(row.original.data.messages);
            return (
              <Text className="truncate" title={text}>
                {text || '—'}
              </Text>
            );
          },
        }),
        accessor('updated_at', {
          header: 'Updated',
          enableSorting: true,
          size: 140,
          cell({ row }) {
            return row.original.updated_at ? (
              <RelativeTime datetime={row.original.updated_at} />
            ) : (
              <Text>—</Text>
            );
          },
        }),
        accessor('data', {
          id: 'status',
          header: 'Status',
          enableSorting: false,
          size: 120,
          cell({ row }) {
            const status = getLatestRunStatus(row.original);
            if (!status) {
              return (
                <Badge color="gray" kind="solid">
                  Never run
                </Badge>
              );
            }
            if (status === 'success') {
              return (
                <Badge color="green" kind="solid">
                  Pass
                </Badge>
              );
            }
            if (status === 'blocked') {
              return (
                <Badge color="red" kind="solid">
                  Fail
                </Badge>
              );
            }
            return (
              <Badge color="gray" kind="solid">
                Unknown
              </Badge>
            );
          },
        }),
        accessor('data', {
          id: 'run',
          header: '',
          enableSorting: false,
          size: 96,
          cell({ row }) {
            const check = row.original;
            const isRunning = runMutation.isPending && runMutation.variables?.check.id === check.id;
            return (
              <LoadingButton
                kind="secondary"
                height={28}
                loading={isRunning}
                disabled={runMutation.isPending}
                onClick={(e) => {
                  e.stopPropagation();
                  runMutation.mutate({ workspace, check });
                }}
              >
                Run
              </LoadingButton>
            );
          },
        }),
      ],
      [runMutation, workspace]
    );

  return (
    <StudioDataView
      dataViewState={dataViewState}
      makeColumns={makeColumns}
      onRowClick={(check) => navigate(getGuardrailCheckRoute(workspace, configName, check.name))}
      attributes={{
        DataViewRoot: {
          data: data?.data ?? [],
          totalCount: pagination?.total_results,
          requestStatus: error ? 'error' : isFetching ? 'loading' : undefined,
        },
        DataViewTableContent: {
          renderEmptyState: () => (
            <TableEmptyState
              icon={<ListChecks className="h-[64px] w-[64px]" />}
              header="No checks yet"
              emptyMessage="Checks let you test this guardrail against sample inputs. Creating checks is coming soon."
            />
          ),
          renderErrorState: () => (
            <ErrorPanel
              errorMessage={getErrorMessage(error ?? new Error('Failed to fetch guardrail checks'))}
            />
          ),
        },
      }}
    />
  );
};
