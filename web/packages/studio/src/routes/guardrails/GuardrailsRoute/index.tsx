/*
 * SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 *
 * NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
 * property and proprietary rights in and to this material, related
 * documentation and any modifications thereto. Any use, reproduction,
 * disclosure or distribution of this material and related documentation
 * without an express license agreement from NVIDIA CORPORATION or
 * its affiliates is strictly prohibited.
 */

import {
  getGuardrailsGetGuardrailConfigQueryKey,
  useGuardrailsDeleteConfig,
} from '@nemo/sdk/generated/platform/api';
import type { GuardrailConfig } from '@nemo/sdk/generated/platform/schema';
import { PageHeader, Stack } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { GuardrailsDataView } from '@studio/components/dataViews/GuardrailsDataView';
import { DeleteConfirmationModal } from '@studio/components/DeleteConfirmationModal';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { getGuardrailDetailRoute, getGuardrailsRoute } from '@studio/routes/utils';
import { useQueryClient } from '@tanstack/react-query';
import { type FC, useCallback, useState } from 'react';
import { useNavigate } from 'react-router-dom';

export const GuardrailsRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const [configToDelete, setConfigToDelete] = useState<GuardrailConfig | null>(null);

  const { mutateAsync: deleteConfig } = useGuardrailsDeleteConfig();

  useBreadcrumbs({
    items: [{ href: getGuardrailsRoute(workspace), slotLabel: 'Guardrails' }],
  });

  const handleDelete = useCallback(async (): Promise<boolean> => {
    if (!configToDelete?.name) return false;
    try {
      await deleteConfig({ workspace, name: configToDelete.name });
      // Invalidate by URL prefix — matches all pages/sorts for this workspace
      await queryClient.invalidateQueries({
        queryKey: [`/apis/guardrails/v2/workspaces/${workspace}/configs`],
      });
      return true;
    } catch {
      return false;
    }
  }, [configToDelete, deleteConfig, queryClient, workspace]);

  return (
    <AccessibleTitle title="Guardrails">
      <Stack className="h-full overflow-auto" gap="density-2xl" padding="density-2xl">
        <PageHeader
          className="p-0"
          slotHeading="Guardrail Configs"
          slotDescription="Manage NeMo Guardrails configurations for your workspace."
        />
        <GuardrailsDataView
          workspace={workspace}
          onRowClick={(config) => {
            if (!config.name) return;
            queryClient.setQueryData(
              getGuardrailsGetGuardrailConfigQueryKey(workspace, config.name),
              config
            );
            navigate(getGuardrailDetailRoute(workspace, config.name));
          }}
          onRequestDelete={setConfigToDelete}
        />
      </Stack>

      {configToDelete ? (
        <DeleteConfirmationModal
          open
          simpleConfirm
          title={`Delete guardrail config: ${configToDelete.name}`}
          successText="Guardrail config deleted successfully."
          errorText="Failed to delete the guardrail config. Please try again."
          onDelete={handleDelete}
          onClose={() => setConfigToDelete(null)}
        />
      ) : null}
    </AccessibleTitle>
  );
};
