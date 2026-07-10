/*
 * SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */

import { KVPair } from '@nemo/common/src/components/KVPair';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { useGuardrailsGetGuardrailConfig } from '@nemo/sdk/generated/platform/api';
import { Stack, Text } from '@nvidia/foundations-react-core';
import { countRails } from '@studio/components/dataViews/GuardrailsDataView/guardrailUtils';
import { Loading } from '@studio/components/Layouts/Loading';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useRequiredPathParams } from '@studio/util/hooks/useRequiredPathParams';
import { type FC } from 'react';

export const GuardrailDetailsTab: FC = () => {
  const workspace = useWorkspaceFromPath();
  const { guardrailConfigName } = useRequiredPathParams([ROUTE_PARAMS.guardrailConfigName]);

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
    return <Text className="text-feedback-danger">Failed to load guardrail config.</Text>;
  }

  const modelCount = config.data?.models?.length ?? 0;
  const railCount = countRails(config.data);

  return (
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
        <KVPair label="Models" orientation="horizontal" size="medium" value={String(modelCount)} />
        <KVPair label="Rails" orientation="horizontal" size="medium" value={String(railCount)} />
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
  );
};
