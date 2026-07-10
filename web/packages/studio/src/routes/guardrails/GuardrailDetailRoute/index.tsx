/*
 * SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */

import {
  useGuardrailsDeleteConfig,
  useGuardrailsGetGuardrailConfig,
} from '@nemo/sdk/generated/platform/api';
import { Button, Flex, PageHeader, Stack, Tabs, Text } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { DeleteConfirmationModal } from '@studio/components/DeleteConfirmationModal';
import { Loading } from '@studio/components/Layouts/Loading';
import { ROUTE_PARAMS, ROUTES } from '@studio/constants/routes';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import {
  getGuardrailChatRoute,
  getGuardrailDetailsRoute,
  getGuardrailsRoute,
} from '@studio/routes/utils';
import { useRequiredPathParams } from '@studio/util/hooks/useRequiredPathParams';
import { useQueryClient } from '@tanstack/react-query';
import { type FC, Suspense, useCallback, useState } from 'react';
import { Link, Outlet, matchPath, useLocation, useNavigate } from 'react-router-dom';

export const GuardrailDetailRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { guardrailConfigName } = useRequiredPathParams([ROUTE_PARAMS.guardrailConfigName]);

  const [showDelete, setShowDelete] = useState(false);

  const location = useLocation();
  const match = matchPath(
    { path: `${ROUTES.workspace.guardrailDetail}/:selectedTab`, end: false },
    location.pathname
  );
  const {
    params: { selectedTab },
  } = match ?? { params: { selectedTab: 'details' } };

  const detailsRoute = getGuardrailDetailsRoute(workspace, guardrailConfigName);
  const chatRoute = getGuardrailChatRoute(workspace, guardrailConfigName);

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

        <Tabs
          // Override KUI's default overflow:hidden since we're using Tabs purely for
          // navigation (with renderLink), not for containing tab panel content.
          className="overflow-visible"
          value={selectedTab}
          items={[
            { value: 'details', children: 'Details', href: detailsRoute },
            { value: 'chat', children: 'Chat', href: chatRoute },
          ]}
          renderLink={(item) => <Link to={item.href!}>{item.children}</Link>}
        />

        <Suspense fallback={<Loading description="Loading..." />}>
          <Outlet />
        </Suspense>
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
