// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { Adapter, ModelEntity } from '@nemo/sdk/generated/platform/schema';
import { Button, Flex, PageHeader, Stack } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { CustomModelsDataView } from '@studio/components/dataViews/CustomModelsDataView';
import { CustomizeModelButton } from '@studio/components/dataViews/CustomModelsDataView/CustomizeModelButton';
import { ModelPanel, ModelPanelTab } from '@studio/components/sidePanels/ModelPanels/ModelPanel';
import { INTAKE_ENABLED } from '@studio/constants/environment';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { getEvaluationResultsRoute, getIntakeTracesRoute } from '@studio/routes/utils';
import { type FC, useState } from 'react';
import { useNavigate } from 'react-router-dom';

export const CustomizationJobListRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const navigate = useNavigate();
  const [selectedModel, setSelectedModel] = useState<ModelEntity | null>(null);
  const [selectedAdapter, setSelectedAdapter] = useState<Adapter | null>(null);
  const [selectedTab, setSelectedTab] = useState<'model-details' | 'chat-playground'>(
    'model-details'
  );

  useBreadcrumbs({
    items: [
      {
        slotLabel: 'Custom Models',
      },
    ],
  });

  return (
    <AccessibleTitle title={`Custom Models for ${workspace}`}>
      <Stack className="h-full" gap="density-2xl" padding="density-2xl">
        <PageHeader
          className="p-0"
          slotHeading="Custom Models"
          slotDescription="Create, manage, and deploy custom AI models with fine-tuning and prompt tuning."
          slotActions={<CustomizeModelButton workspace={workspace} />}
        />
        <CustomModelsDataView
          workspace={workspace}
          onRowClick={(model: ModelEntity, tab: ModelPanelTab, adapter?: Adapter) => {
            setSelectedModel(model);
            setSelectedAdapter(adapter ?? null);
            setSelectedTab(tab);
          }}
        />
      </Stack>
      <ModelPanel
        open={!!selectedModel}
        model={selectedModel ?? undefined}
        adapter={selectedAdapter}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedModel(null);
            setSelectedAdapter(null);
          }
        }}
        defaultTab={selectedTab}
        overviewProps={{
          slotActions: (
            <Flex gap="density-md" align="center">
              {selectedModel && (
                <CustomizeModelButton model={selectedModel} workspace={workspace} />
              )}
              {INTAKE_ENABLED && (
                <Button
                  className="flex-1"
                  kind="secondary"
                  size="small"
                  onClick={() => {
                    navigate(getIntakeTracesRoute(workspace));
                  }}
                >
                  View Intake Traces
                </Button>
              )}
              <Button
                className="flex-1"
                kind="secondary"
                size="small"
                onClick={() => {
                  // EvaluationModelSelect treats `URN::adapter` as a single
                  // form-field value, so when an adapter is selected we append
                  navigate(getEvaluationResultsRoute(workspace));
                }}
              >
                Evaluate this Model
              </Button>
            </Flex>
          ),
        }}
      />
    </AccessibleTitle>
  );
};
