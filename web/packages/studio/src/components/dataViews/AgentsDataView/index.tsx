// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Root as DataViewRoot } from '@nemo/common/src/components/DataView/internal';
import {
  ROW_ACTIONS_COLUMN_SIZE,
  StudioDataView,
} from '@nemo/common/src/components/DataView/StudioDataView';
import { ErrorMessage } from '@nemo/common/src/components/ErrorMessage';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState';
import { JOB_POLLING_INTERVAL_LONG } from '@nemo/common/src/constants';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { getSortParamWithWhitelist } from '@nemo/common/src/utils/query';
import {
  getAgentsListAgentsQueryKey,
  useAgentsDeleteAgent,
  useAgentsListAgents,
  useAgentsListDeployments,
} from '@nemo/sdk/generated/agents/api';
import type { Agent } from '@nemo/sdk/generated/agents/schema/Agent';
import type { AgentDeployment } from '@nemo/sdk/generated/agents/schema/AgentDeployment';
import { Text } from '@nvidia/foundations-react-core';
import { getErrorMessage } from '@studio/api/common/utils';
import { getAgentModelNames } from '@studio/components/dataViews/AgentsDataView/utils';
import { DeleteConfirmationModal } from '@studio/components/DeleteConfirmationModal';
import { DocumentationButton } from '@studio/components/DocumentationButton';
import { LINK_DOCS_STUDIO } from '@studio/constants/links';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { keepPreviousData, useQueryClient } from '@tanstack/react-query';
import { HatGlasses } from 'lucide-react';
import { ComponentProps, FC, useMemo, useState } from 'react';

export type { Agent, AgentDeployment };

// Structured shape used by the Agent Optimizer when inspecting NAT workflow
// configs. The platform stores ``Agent.config`` as an arbitrary dict; only the
// optimizer interprets these specific fields.
export interface AgentConfig {
  functions?: Record<string, { _type: string }>;
  llms?: Record<
    string,
    {
      _type: string;
      model_name?: string;
      api_key?: string;
      temperature?: number;
      base_url?: string;
    }
  >;
  workflow?: {
    _type: string;
    tool_names?: string[];
    llm_name?: string;
    verbose?: boolean;
    parse_agent_response_max_retries?: number;
  };
}

// Kept for backward compatibility with consumers (e.g. AgentDeploymentsListRoute)
export type AgentItem = Agent & { id: string };
export type AgentEntity = AgentDeployment & { id: string };

const TERMINAL_DEPLOYMENT_STATUSES = new Set(['running', 'failed', 'stopped', 'error']);

export type AgentTableRow = {
  id: string;
  name: string;
  workspace: string;
  description?: string;
  config?: AgentConfig;
  config_format?: string;
  created_at?: string;
  models: string[];
  deploymentsStatus: string;
  deploymentsDeploying: boolean;
};

const SORTABLE_FIELDS = ['name', 'created_at'] as const;
const DEFAULT_SORT = '-created_at';

type DeleteState = { kind: 'agent'; item: AgentTableRow } | null;

export interface CombinedAgentsTableProps {
  onAgentRowClick?: (agent: AgentTableRow) => void;
  onCreateDeployment?: (agentName: string) => void;
}

export const AgentsTable: FC<CombinedAgentsTableProps> = ({
  onAgentRowClick,
  onCreateDeployment,
}) => {
  const workspace = useWorkspaceFromPath();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [deleteState, setDeleteState] = useState<DeleteState>(null);

  const dataViewState = useStudioDataViewState({
    defaultSort: { id: 'created_at', desc: true },
    columnPinning: {
      right: ['row-actions'],
    },
  });

  const page = dataViewState.pagination.state.pageIndex + 1;
  const pageSize = dataViewState.pagination.state.pageSize;
  const sortParam = getSortParamWithWhitelist(
    dataViewState.sorting.state,
    SORTABLE_FIELDS,
    DEFAULT_SORT
  );

  const {
    data: agentsResponse,
    isLoading: agentsLoading,
    error: agentsError,
  } = useAgentsListAgents(
    workspace,
    { page, page_size: pageSize, sort: sortParam },
    {
      query: {
        placeholderData: keepPreviousData,
        refetchInterval: JOB_POLLING_INTERVAL_LONG,
      },
    }
  );

  const { data: deploymentsResponse } = useAgentsListDeployments(workspace, undefined, {
    query: { refetchInterval: JOB_POLLING_INTERVAL_LONG },
  });

  const agentsData = agentsResponse?.data;
  const totalCount = agentsResponse?.pagination?.total_results ?? agentsData?.length ?? 0;
  const deploymentsData = deploymentsResponse?.data;

  const tableData = useMemo<AgentTableRow[]>(() => {
    const deployments = deploymentsData ?? [];
    return (agentsData ?? []).map((agent) => {
      const agentDeployments = deployments.filter((d) => d.agent === agent.name);
      const total = agentDeployments.length;
      const healthy = agentDeployments.filter((d) => d.status === 'running').length;
      const deploymentsDeploying = agentDeployments.some(
        (d) => d.status && !TERMINAL_DEPLOYMENT_STATUSES.has(d.status) && d.status !== 'deleting'
      );
      const deploymentsStatus = total === 0 ? 'No Deployments' : `${healthy}/${total} Healthy`;
      const config = agent.config as AgentConfig | undefined;
      return {
        id: agent.id ?? agent.name ?? '',
        name: agent.name ?? '',
        workspace: agent.workspace,
        description: agent.description,
        config,
        config_format: agent.config_format,
        created_at: agent.created_at,
        models: getAgentModelNames(config),
        deploymentsStatus,
        deploymentsDeploying,
      };
    });
  }, [agentsData, deploymentsData]);

  const deleteAgentMutation = useAgentsDeleteAgent({
    mutation: {
      onSuccess: () => {
        toast.success('Agent deleted.');
        void queryClient.refetchQueries({
          queryKey: getAgentsListAgentsQueryKey(workspace),
        });
      },
      onError: (error) => {
        if (error.response?.status === 409) {
          toast.error(
            'Agent has active deployments. Please delete all deployments before deleting agent.'
          );
          return;
        }
        toast.error(getErrorMessage(error, 'Failed to delete agent.'));
      },
    },
  });

  const handleDelete = async () => {
    try {
      if (deleteState?.kind === 'agent') {
        await deleteAgentMutation.mutateAsync({
          workspace,
          name: deleteState.item.name,
        });
      }
      return true;
    } catch {
      // Error already surfaced via onError toast
      return false;
    }
  };

  const makeColumns: ComponentProps<typeof DataViewRoot<AgentTableRow>>['makeColumns'] = (
    { accessor },
    { rowActionsColumn }
  ) => [
    accessor('name', {
      header: 'Name',
      enableSorting: true,
    }),
    accessor('description', {
      header: 'Description',
      enableSorting: false,
      cell: ({ row }) => <Text>{row.original.description || '-'}</Text>,
    }),
    accessor('models', {
      header: 'Model',
      enableSorting: false,
      cell: ({ row }) => <Text>{row.original.models.join(', ') || '-'}</Text>,
    }),
    accessor('deploymentsStatus', {
      header: 'Deployments',
      enableSorting: false,
      cell: ({ row }) =>
        row.original.deploymentsDeploying ? (
          <Text>Deploying...</Text>
        ) : (
          <Text>{row.original.deploymentsStatus}</Text>
        ),
    }),
    accessor('created_at', {
      header: 'Created',
      size: 200,
      enableSorting: true,
      cell: ({ row }) =>
        row.original.created_at ? (
          <RelativeTime datetime={row.original.created_at} />
        ) : (
          <Text>-</Text>
        ),
    }),
    rowActionsColumn({
      size: ROW_ACTIONS_COLUMN_SIZE,
      enableResizing: false,
      rowActions: (row: AgentTableRow) => [
        {
          children: 'Deploy',
          onSelect: () => onCreateDeployment?.(row.name),
        },
        { kind: 'divider' as const },
        {
          children: 'Delete',
          danger: true,
          onSelect: () => setDeleteState({ kind: 'agent', item: row }),
        },
      ],
    }),
  ];

  if (agentsError) {
    return <ErrorMessage message="Failed to load agents." />;
  }

  return (
    <>
      <StudioDataView
        dataViewState={dataViewState}
        makeColumns={makeColumns}
        onRowClick={(row: AgentTableRow) => {
          onAgentRowClick?.(row);
        }}
        attributes={{
          DataViewRoot: {
            data: tableData,
            totalCount,
            requestStatus: agentsLoading && !agentsData ? 'loading' : undefined,
          },
          DataViewTableContent: {
            renderEmptyState: () => (
              <TableEmptyState
                header="No Agents Found"
                emptyMessage="No agents have been created yet."
                icon={<HatGlasses className="m-0 size-24" />}
                actions={<DocumentationButton href={LINK_DOCS_STUDIO} />}
              />
            ),
          },
        }}
      />
      {deleteState && (
        <DeleteConfirmationModal
          open
          title="Delete Agent"
          onDelete={handleDelete}
          onClose={() => setDeleteState(null)}
          simpleConfirm
          suppressResultToasts
        />
      )}
    </>
  );
};
