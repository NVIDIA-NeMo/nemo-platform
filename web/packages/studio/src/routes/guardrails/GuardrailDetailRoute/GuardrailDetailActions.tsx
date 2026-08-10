// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useGuardrailsDeleteConfig } from '@nemo/sdk/generated/platform/api';
import type { GuardrailConfig } from '@nemo/sdk/generated/platform/schema';
import { DeleteConfirmationModal } from '@studio/components/DeleteConfirmationModal';
import {
  type QuickActionItem,
  QuickActionsMenuRoot,
} from '@studio/components/QuickActionsMenu/QuickActionsMenuRoot';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { getGuardrailsRoute } from '@studio/routes/utils';
import { useQueryClient } from '@tanstack/react-query';
import { type FC, useCallback, useMemo, useState } from 'react';
import { useNavigate } from 'react-router';

interface GuardrailDetailActionsProps {
  config: GuardrailConfig;
}

export const GuardrailDetailActions: FC<GuardrailDetailActionsProps> = ({ config }) => {
  const workspace = useWorkspaceFromPath();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [showDeleteModal, setShowDeleteModal] = useState(false);

  const { mutateAsync: deleteConfig } = useGuardrailsDeleteConfig();

  const handleDelete = useCallback(async (): Promise<boolean> => {
    if (!config.name) return false;
    try {
      await deleteConfig({ workspace, name: config.name });
      await queryClient.invalidateQueries({
        queryKey: [`/apis/guardrails/v2/workspaces/${workspace}/configs`],
      });
      void navigate(getGuardrailsRoute(workspace));
      return true;
    } catch {
      return false;
    }
  }, [config.name, deleteConfig, navigate, queryClient, workspace]);

  const actions = useMemo<QuickActionItem[]>(
    () => [
      {
        label: 'Delete',
        onSelect: () => setShowDeleteModal(true),
        danger: true,
      },
    ],
    []
  );

  return (
    <>
      <QuickActionsMenuRoot actions={actions} />
      {showDeleteModal ? (
        <DeleteConfirmationModal
          open
          simpleConfirm
          title={`Delete guardrail config: ${config.name}`}
          successText="Guardrail config deleted successfully."
          errorText="Failed to delete the guardrail config. Please try again."
          onDelete={handleDelete}
          onClose={() => setShowDeleteModal(false)}
        />
      ) : null}
    </>
  );
};
