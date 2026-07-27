// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { StudioDataView } from '@nemo/common/src/components/DataView/StudioDataView';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { getSortParam } from '@nemo/common/src/utils/query';
import {
  getIronSwarmListManifestsQueryKey,
  useIronSwarmDeleteManifest,
  useIronSwarmListManifests,
} from '@nemo/sdk/generated/iron-swarm/api';
import type { IronSwarmManifest } from '@nemo/sdk/generated/iron-swarm/schema';
import { Button, Text } from '@nvidia/foundations-react-core';
import { DeleteConfirmationModal } from '@studio/components/DeleteConfirmationModal';
import { useRunWarGame } from '@studio/components/ironSwarm/useRunWarGame';
import { QuickActionsMenuRoot } from '@studio/components/QuickActionsMenu/QuickActionsMenuRoot';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import {
  getIronSwarmManifestDetailRoute,
  getNewIronSwarmManifestRoute,
} from '@studio/routes/utils';
import { keepPreviousData, useQueryClient } from '@tanstack/react-query';
import { ComponentProps, FC, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

type IronSwarmManifestWithId = IronSwarmManifest & { id: string };

export const IronSwarmManifestsDataView: FC = () => {
  const navigate = useNavigate();
  const workspace = useWorkspaceFromPath();
  const toast = useToast();
  const queryClient = useQueryClient();
  const dataViewState = useStudioDataViewState({ defaultSort: [{ id: 'created_at', desc: true }] });
  const [toDelete, setToDelete] = useState<IronSwarmManifestWithId | null>(null);

  const { data: response, isLoading } = useIronSwarmListManifests(
    workspace,
    {
      sort: getSortParam(dataViewState.sorting.state),
      page: dataViewState.pagination.state.pageIndex + 1,
      page_size: dataViewState.pagination.state.pageSize,
    },
    { query: { placeholderData: keepPreviousData, refetchOnMount: 'always', retry: false } }
  );

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: getIronSwarmListManifestsQueryKey(workspace) });

  const runWarGame = useRunWarGame(workspace);
  const deleteManifest = useIronSwarmDeleteManifest();

  // A war-game replays the manifest's benign suite, so require one first: with none, send the user to the
  // manifest page to generate it rather than silently kicking off an inline interview mid-run.
  const startRun = (manifest: IronSwarmManifestWithId) => {
    if (!manifest.name) return;
    if (!manifest.benign_suite?.length) {
      toast.error(
        'No benign suite for this manifest yet — generate it first, then run the war-game.'
      );
      navigate(getIronSwarmManifestDetailRoute(workspace, manifest.name));
      return;
    }
    runWarGame.mutate({
      workspace,
      data: { spec: { manifest_id: manifest.name, driver: 'service' } },
    });
  };

  const manifests = useMemo<IronSwarmManifestWithId[]>(() => {
    const rows = (response?.data ?? []) as IronSwarmManifest[];
    return rows.map((m) => ({ ...m, id: m.id || `${m.workspace ?? ''}/${m.name ?? ''}` }));
  }, [response]);

  const total =
    (response?.pagination as { total_results?: number } | undefined)?.total_results ??
    manifests.length;

  const makeColumns: ComponentProps<
    typeof StudioDataView<IronSwarmManifestWithId>
  >['makeColumns'] = ({ accessor }, { rowActionsColumn }) => [
    accessor('name', { header: 'Manifest', cell: ({ row }) => row.original.name ?? '-' }),
    accessor('agent', {
      header: 'Agent',
      cell: ({ row }) => (
        <Text className="max-w-[240px] truncate" kind="body/regular/md">
          {row.original.agent || '-'}
        </Text>
      ),
    }),
    accessor('source_type', {
      header: 'Source',
      size: 120,
      cell: ({ row }) => row.original.source_type ?? 'agent',
    }),
    accessor('created_at', {
      id: 'created_at',
      header: 'Created',
      enableSorting: true,
      size: 160,
      cell: ({ row }) =>
        row.original.created_at ? <RelativeTime datetime={row.original.created_at} /> : null,
    }),
    rowActionsColumn({
      size: 70,
      cell: ({ row }) => (
        <QuickActionsMenuRoot
          actions={[
            { label: 'Run war-game', onSelect: () => startRun(row.original) },
            {
              label: 'Edit',
              onSelect: () =>
                row.original.name &&
                navigate(getIronSwarmManifestDetailRoute(workspace, row.original.name)),
            },
            { label: 'Delete', onSelect: () => setToDelete(row.original) },
          ]}
        />
      ),
    }),
  ];

  return (
    <>
      <StudioDataView<IronSwarmManifestWithId>
        dataViewState={dataViewState}
        makeColumns={makeColumns}
        onRowClick={(row) =>
          row.name && navigate(getIronSwarmManifestDetailRoute(workspace, row.name))
        }
        attributes={{
          DataViewRoot: {
            data: manifests,
            totalCount: total,
            requestStatus: isLoading && !response ? 'loading' : undefined,
          },
          DataViewTableContent: {
            renderEmptyState: () => (
              <TableEmptyState
                header="No manifests yet"
                emptyMessage="Create a manifest from a deployed agent, then run the war-game against it."
                actions={
                  <Button asChild color="brand">
                    <Link to={getNewIronSwarmManifestRoute(workspace)}>New Manifest</Link>
                  </Button>
                }
              />
            ),
          },
        }}
      />
      <DeleteConfirmationModal
        open={!!toDelete}
        onClose={() => setToDelete(null)}
        title={`Delete ${toDelete?.name ?? 'manifest'}?`}
        description="This permanently deletes the manifest and its cached benign suite."
        successText="Manifest deleted."
        errorText="Failed to delete the manifest."
        onDelete={async () => {
          if (!toDelete?.name) return false;
          await deleteManifest.mutateAsync({ workspace, name: toDelete.name });
          invalidate();
          return true;
        }}
      />
    </>
  );
};
