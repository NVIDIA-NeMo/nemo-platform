/*
 * SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */

import { KVPair } from '@nemo/common/src/components/KVPair';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import {
  useGuardrailsDeleteConfig,
  useGuardrailsGetGuardrailConfig,
} from '@nemo/sdk/generated/platform/api';
import { Button, Flex, PageHeader, Stack, Text } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { countRails } from '@studio/components/dataViews/GuardrailsDataView/guardrailUtils';
import { DeleteConfirmationModal } from '@studio/components/DeleteConfirmationModal';
import { Loading } from '@studio/components/Layouts/Loading';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { getGuardrailsRoute } from '@studio/routes/utils';
import { useRequiredPathParams } from '@studio/util/hooks/useRequiredPathParams';
import { useQueryClient } from '@tanstack/react-query';
import { type FC, useCallback, useState } from 'react';
import { useNavigate } from 'react-router-dom';

export const GuardrailDetailRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { guardrailConfigName } = useRequiredPathParams([ROUTE_PARAMS.guardrailConfigName]);

  const [showDelete, setShowDelete] = useState(false);

  useBreadcrumbs({
    items: [
      { href: getGuardrailsRoute(workspace), slotLabel: 'Guardrails' },
      { slotLabel: guardrailConfigName },
    ],
  });

  const queryEnabled = Boolean(workspace && guardrailConfigName);
  const {
    data: config,
    isPending,
    isError,
  } = useGuardrailsGetGuardrailConfig(workspace, guardrailConfigName, {
    query: { enabled: queryEnabled },
  });

  const { mutateAsync: deleteConfig } = useGuardrailsDeleteConfig();

  const handleDelete = useCallback(async (): Promise<boolean> => {
    try {
      await deleteConfig({ workspace, name: guardrailConfigName });
      // Invalidate by URL prefix — matches all pages/sorts for this workspace.
      await queryClient.invalidateQueries({
        queryKey: [`/apis/guardrails/v2/workspaces/${workspace}/configs`],
      });
      navigate(getGuardrailsRoute(workspace));
      return true;
    } catch {
      return false;
    }
  }, [deleteConfig, guardrailConfigName, navigate, queryClient, workspace]);

  if (isPending) {
    return <Loading description="Loading guardrail config..." />;
  }

  if (isError || !config) {
    return (
      <AccessibleTitle title={`Guardrail config ${guardrailConfigName}`}>
        <Stack className="w-full h-full min-h-0 p-density-2xl" gap="density-xl">
          <PageHeader slotHeading={guardrailConfigName} />
          <Text className="text-feedback-danger">Failed to load guardrail config.</Text>
        </Stack>
      </AccessibleTitle>
    );
  }

  const modelCount = config.data?.models?.length ?? 0;
  const railCount = countRails(config.data);

  return (
    <AccessibleTitle title={`Guardrail config ${guardrailConfigName}`}>
      <Stack className="w-full min-h-full p-density-2xl" gap="density-xl">
        <PageHeader
          slotHeading={
            <Flex gap="density-sm" align="center" justify="between">
              <span className="min-w-0 truncate" title={config.name}>
                {config.name}
              </span>
              <Flex gap="density-sm">
                <Button kind="secondary" disabled title="Edit — coming soon">
                  Edit
                </Button>
                <Button kind="secondary" color="danger" onClick={() => setShowDelete(true)}>
                  Delete
                </Button>
              </Flex>
            </Flex>
          }
        />

        <Stack className="gap-density-lg">
          <Stack className="gap-density-md">
            {config.description ? (
              <KVPair
                label="Description"
                orientation="horizontal"
                size="medium"
                truncate={false}
                value={config.description}
              />
            ) : null}
            <KVPair
              label="Models"
              orientation="horizontal"
              size="medium"
              value={String(modelCount)}
            />
            <KVPair
              label="Rails"
              orientation="horizontal"
              size="medium"
              value={String(railCount)}
            />
            <KVPair
              label="Created"
              orientation="horizontal"
              size="medium"
              value={
                config.created_at ? (
                  <RelativeTime datetime={config.created_at} focusableForTooltip={false} />
                ) : (
                  '—'
                )
              }
            />
            <KVPair
              label="Updated"
              orientation="horizontal"
              size="medium"
              value={
                config.updated_at ? (
                  <RelativeTime datetime={config.updated_at} focusableForTooltip={false} />
                ) : (
                  '—'
                )
              }
            />
          </Stack>

          {config.data ? (
            <Stack gap="density-sm">
              <Text kind="label/bold/sm">Config</Text>
              <pre className="overflow-auto rounded bg-surface-raised p-density-md text-xs leading-relaxed">
                {JSON.stringify(config.data, null, 2)}
              </pre>
            </Stack>
          ) : null}
        </Stack>
      </Stack>

      {showDelete ? (
        <DeleteConfirmationModal
          open
          simpleConfirm
          title={`Delete guardrail config: ${config.name}`}
          successText="Guardrail config deleted successfully."
          errorText="Failed to delete the guardrail config. Please try again."
          onDelete={handleDelete}
          onClose={() => setShowDelete(false)}
        />
      ) : null}
    </AccessibleTitle>
  );
};
