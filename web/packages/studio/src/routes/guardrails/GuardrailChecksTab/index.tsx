// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useGuardrailsGetGuardrailConfig } from '@nemo/sdk/generated/platform/api';
import { Flex, Text } from '@nvidia/foundations-react-core';
import { useGuardrailChecksForConfig } from '@studio/api/guardrail-checks/hooks';
import { Loading } from '@studio/components/Layouts/Loading';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { GuardrailTestCasesEditor } from '@studio/routes/guardrails/GuardrailChecksTab/GuardrailTestCasesEditor';
import { useRequiredPathParams } from '@studio/util/hooks/useRequiredPathParams';
import type { FC } from 'react';

export const GuardrailChecksTab: FC = () => {
  const workspace = useWorkspaceFromPath();
  const { guardrailConfigName } = useRequiredPathParams([ROUTE_PARAMS.guardrailConfigName]);

  const { data: config, isPending: isConfigPending } = useGuardrailsGetGuardrailConfig(
    workspace,
    guardrailConfigName,
    { query: { enabled: Boolean(workspace && guardrailConfigName) } }
  );

  const {
    data: checksPage,
    isPending: isChecksPending,
    isError: isChecksError,
  } = useGuardrailChecksForConfig(
    workspace,
    config?.id ?? '',
    { page_size: 1000 },
    { enabled: Boolean(config?.id) }
  );

  if (isConfigPending || isChecksPending) {
    return <Loading description="Loading checks..." />;
  }
  // Unreachable in-app: GuardrailDetailRoute runs the same config query and renders its own
  // error state instead of this <Outlet />. Kept so `config.id` narrows below.
  if (!config?.name) {
    return null;
  }
  // Never fall back to an empty list here — an editor showing "Run 0 Tests" is indistinguishable
  // from a config that genuinely has no test cases, so a failed fetch would read as data loss.
  if (isChecksError || !checksPage) {
    return (
      <Flex
        className="w-full min-h-80"
        align="center"
        justify="center"
        data-testid="guardrail-checks-tab"
      >
        <Text className="text-feedback-danger">Failed to load guardrail tests.</Text>
      </Flex>
    );
  }

  return (
    <GuardrailTestCasesEditor workspace={workspace} configId={config.id} checks={checksPage.data} />
  );
};
