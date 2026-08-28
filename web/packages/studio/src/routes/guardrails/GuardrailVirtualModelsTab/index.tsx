// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Stack, Text } from '@nvidia/foundations-react-core';
import { VirtualModelsDataView } from '@studio/components/dataViews/VirtualModelsDataView';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useRequiredPathParams } from '@studio/util/hooks/useRequiredPathParams';
import type { FC } from 'react';

/**
 * The Virtual Models tab: the inference routes that apply this guardrail config.
 *
 * Renders the same grid as the standalone Virtual Models page, scoped by
 * `filter[guardrail_config]`, so a row behaves identically here — details, chat, and
 * delete all come from the shared data view rather than a parallel implementation.
 */
export const GuardrailVirtualModelsTab: FC = () => {
  const workspace = useWorkspaceFromPath();
  const { guardrailConfigName } = useRequiredPathParams([ROUTE_PARAMS.guardrailConfigName]);

  // Config references are fully qualified, so a virtual model in any workspace may
  // appear here. Matches how the API stores and matches the reference.
  const configRef = `${workspace}/${guardrailConfigName}`;

  return (
    <Stack className="h-full min-h-0" gap="density-md">
      <Text kind="body/regular/sm" className="text-secondary">
        Inference routes that apply this guardrail config to requests or responses.
      </Text>

      <VirtualModelsDataView
        workspace={workspace}
        guardrailConfig={configRef}
        attributes={{
          Stack: {
            className: 'flex-1 min-h-0',
          },
        }}
      />
    </Stack>
  );
};
