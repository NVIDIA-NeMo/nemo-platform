// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  RelativeTime,
  StatusBadge,
  StudioDataView,
  TableEmptyState,
  useStudioDataViewState,
} from "@nemo/common";
import { Stack, Text } from "@nvidia/foundations-react-core";
import { useCallback, useEffect, type ComponentProps } from "react";
import { pluginPath } from "./paths";
import type { PluginHost, Workspace } from "./types";

// `@nemo/common` is external like react — this is Studio's own StudioDataView,
// not a copy. Bare specifier only.
export function SharedUiPage({ host }: { host: PluginHost }) {
  const { data, isPending, isError } =
    host.sdk.platform.useEntitiesListWorkspaces({
      page: 1,
      page_size: 100,
    });
  const workspaces = data?.data ?? [];

  // Renders in Studio's chrome, outside this subtree. Studio clears it on unmount.
  const { set: setBreadcrumbs } = host.breadcrumbs;
  const { workspaceId } = host;
  useEffect(() => {
    setBreadcrumbs([
      { label: "Example Plugin", href: pluginPath(workspaceId, "overview") },
      { label: "Shared UI" },
    ]);
  }, [setBreadcrumbs, workspaceId]);

  // Syncs to URL search params — one DataView per route or they fight.
  const dataViewState = useStudioDataViewState();

  const makeColumns = useCallback<
    ComponentProps<typeof StudioDataView<Workspace>>["makeColumns"]
  >(
    (col) => [
      col.accessor("name", { header: "Name", size: 240 }),
      col.display({
        id: "status",
        header: "Status",
        size: 120,
        cell: ({ row }) => <StatusBadge status={row.original.status ?? "ready"} />,
      }),
      col.display({
        id: "created",
        header: "Created",
        size: 160,
        cell: ({ row }) =>
          row.original.created_at ? (
            <RelativeTime datetime={row.original.created_at} />
          ) : (
            <Text kind="body/regular/sm" color="secondary">
              —
            </Text>
          ),
      }),
    ],
    [],
  );

  return (
    <Stack gap="2">
      <Text kind="label/bold/md">Shared UI</Text>
      <Text kind="body/regular/sm" color="secondary">
        This table is Studio&apos;s own StudioDataView, imported from
        @nemo/common and resolved through Studio&apos;s import map — not a copy
        bundled into the plugin.
      </Text>

      {isError ? (
        <TableEmptyState
          header="Couldn't load workspaces"
          emptyMessage="The request failed. Try again."
        />
      ) : !isPending && workspaces.length === 0 ? (
        <TableEmptyState
          header="No workspaces"
          emptyMessage="Create a workspace to see it listed here."
        />
      ) : (
        <Stack className="min-h-[320px]">
          <StudioDataView
            dataViewState={dataViewState}
            makeColumns={makeColumns}
            attributes={{
              DataViewRoot: {
                data: workspaces,
                totalCount: workspaces.length,
                reactTableOptions: { getRowId: (row) => row.name },
              },
            }}
          />
        </Stack>
      )}
    </Stack>
  );
}
