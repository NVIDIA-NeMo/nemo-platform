/*
 * SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */

import { useGuardrailsGetGuardrailConfig } from '@nemo/sdk/generated/platform/api';
import { Flex, PageHeader, Stack, Tabs, Text } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { Loading } from '@studio/components/Layouts/Loading';
import { ROUTE_PARAMS, ROUTES } from '@studio/constants/routes';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { GuardrailFormProvider } from '@studio/routes/guardrails/GuardrailForm/GuardrailFormProvider';
import { GuardrailHeaderActions } from '@studio/routes/guardrails/GuardrailForm/GuardrailHeaderActions';
import { getGuardrailConfigRoute, getGuardrailsRoute } from '@studio/routes/utils';
import { useRequiredPathParams } from '@studio/util/hooks/useRequiredPathParams';
import { type FC, Suspense } from 'react';
import { Link, Outlet, matchPath, useLocation } from 'react-router-dom';

export const GuardrailDetailRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const { guardrailConfigName } = useRequiredPathParams([ROUTE_PARAMS.guardrailConfigName]);

  const location = useLocation();
  const match = matchPath(
    { path: `${ROUTES.workspace.guardrailDetail}/:selectedTab`, end: false },
    location.pathname
  );
  const {
    params: { selectedTab },
  } = match ?? { params: { selectedTab: 'config' } };

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
      <GuardrailFormProvider config={config}>
        <Stack className="w-full min-h-full p-density-2xl" gap="density-xl">
          <PageHeader
            slotHeading={
              <Flex gap="density-sm" align="center" justify="between">
                <span className="min-w-0 truncate" title={config.name}>
                  {config.name}
                </span>
                <GuardrailHeaderActions />
              </Flex>
            }
          />

          <Tabs
            // Tabs used purely for navigation (renderLink); override KUI's default overflow:hidden.
            className="overflow-visible"
            value={selectedTab}
            items={[
              {
                value: 'config',
                children: 'Configuration',
                href: getGuardrailConfigRoute(workspace, guardrailConfigName),
              },
            ]}
            renderLink={(item) => <Link to={item.href!}>{item.children}</Link>}
          />

          <Suspense fallback={<Loading description="Loading..." />}>
            <Outlet />
          </Suspense>
        </Stack>
      </GuardrailFormProvider>
    </AccessibleTitle>
  );
};
