// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useGuardrailsGetGuardrailConfig } from '@nemo/sdk/generated/platform/api';
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

  const { data: checksPage, isPending: isChecksPending } = useGuardrailChecksForConfig(
    workspace,
    config?.id ?? '',
    { page_size: 1000 },
    { enabled: Boolean(config?.id) }
  );

  if (isConfigPending || isChecksPending) {
    return <Loading description="Loading checks..." />;
  }
  if (!config?.name) {
    return null;
  }

  return (
    <GuardrailTestCasesEditor
      workspace={workspace}
      configId={config.id}
      configName={config.name}
      checks={checksPage?.data ?? []}
    />
  );
};
