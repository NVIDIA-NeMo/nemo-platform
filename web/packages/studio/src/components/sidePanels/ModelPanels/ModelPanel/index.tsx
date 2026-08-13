// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DeleteConfirmationModal } from '@nemo/common/src/components/DeleteConfirmationModal';
import {
  getModelsListModelsQueryKey,
  getProviderProxyGetQueryKey,
  useModelsDeleteModel,
} from '@nemo/sdk/generated/platform/api';
import {
  type Adapter,
  type ModelDeployment,
  type ModelEntity,
} from '@nemo/sdk/generated/platform/schema';
import {
  Block,
  Button,
  Flex,
  SegmentedControl,
  SidePanel,
  Stack,
} from '@nvidia/foundations-react-core';
import { Empty } from '@studio/components/Empty';
import { Loading } from '@studio/components/Layouts/Loading';
import { ModelChat } from '@studio/components/ModelChat';
import {
  ModelArtifactData,
  ModelDetailOverview,
  ModelDetailOverviewProps,
  ModelParametersAccordion,
} from '@studio/components/sidePanels/ModelPanels/ModelPanel/components';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { useModelChatAvailability } from '@studio/hooks/useModelChatAvailability';
import { useQueryClient } from '@tanstack/react-query';
import {
  type ComponentProps,
  type FC,
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react';

export type ModelPanelTab = 'model-details' | 'chat-playground';

export interface ModelPanelProps {
  /** Model entity from the platform API */
  model?: ModelEntity;
  /** When provided, the panel highlights this adapter within the model */
  adapter?: Adapter | null;
  /** Whether the model is loading */
  loading?: boolean;
  /** Optional props for ModelDetailOverview (description, tags, status override) */
  overviewProps?: Omit<ModelDetailOverviewProps, 'model'>;
  /** When available, deployment for this model (enables Status in Artifact Data) */
  deployment?: ModelDeployment | null;
  /** Optional artifact fields from another source (Backend Engine, GPU Architecture, Tensor Parallelism) */
  artifactData?: ModelArtifactData | null;
  /** Hides Customizer-specific details when the Customizer feature is disabled. */
  showCustomizationDetails?: boolean;
  /** When available, customization job ID for this model (enables "View Job Details" in Customization section) */
  customizationJobId?: string | null;
  /** Controlled open state; when provided with onOpenChange, panel can be closed by the user */
  open?: boolean;
  /** Called when the panel open state changes (e.g. user closes the panel) */
  onOpenChange?: (open: boolean) => void;
  /** When provided, switches the active tab; the panel syncs to this value on change */
  defaultTab?: ModelPanelTab;
  /** Called when the user switches tab (e.g. for syncing to URL) */
  onTabChange?: (tab: ModelPanelTab) => void;
  /**
   * When true, shows a footer control to delete the model entity (hidden while viewing an adapter
   * row or when the panel is loading / has no model).
   */
  allowModelDelete?: boolean;
  /** Optional hook after a successful model delete (e.g. clear local selection). */
  onModelDeleted?: () => void;
  attributes?: {
    SidePanel?: ComponentProps<typeof SidePanel>;
    SegmentedControl?: ComponentProps<typeof SegmentedControl>;
  };
}

/**
 * Side panel section for model details: "Model Parameters".
 * Displays Creator, Architecture, Context Size, Parameters,
 * Fine-tune Options, Recommended GPUs, Default Name, and Version.
 */
export const ModelPanel: FC<ModelPanelProps> = ({
  model,
  adapter,
  loading,
  overviewProps,
  deployment,
  artifactData,
  showCustomizationDetails = true,
  customizationJobId,
  open = true,
  onOpenChange,
  defaultTab,
  onTabChange,
  allowModelDelete = false,
  onModelDeleted,
  attributes,
}) => {
  const queryClient = useQueryClient();
  const { mutateAsync: deleteModel } = useModelsDeleteModel();
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const { modelChatStatus, isLoading: isChatStatusLoading } = useModelChatAvailability(model, {
    adapter,
  });

  const [selectedTab, setSelectedTab] = useState<ModelPanelTab>(defaultTab ?? 'model-details');
  const tabItems = useMemo(
    () => [
      { value: 'model-details', children: 'Model Details' },
      { value: 'chat-playground', children: 'Chat Playground' },
    ],
    []
  );

  useEffect(() => {
    if (defaultTab) {
      setSelectedTab(defaultTab);
    }
  }, [defaultTab]);

  useEffect(() => {
    setDeleteModalOpen(false);
  }, [model?.name, model?.workspace, open]);

  const handleTabChange = (value: string) => {
    const tab = value as ModelPanelTab;
    setSelectedTab(tab);
    onTabChange?.(tab);
  };

  const handleDeleteModel = useCallback(async () => {
    if (!model?.name || !model.workspace) return false;
    try {
      await deleteModel({ workspace: model.workspace, name: model.name });
      await queryClient.invalidateQueries({
        queryKey: getModelsListModelsQueryKey(model.workspace, {}),
      });
      onModelDeleted?.();
      onOpenChange?.(false);
      return true;
    } catch {
      return false;
    }
  }, [deleteModel, model?.name, model?.workspace, onModelDeleted, onOpenChange, queryClient]);

  const showDeleteControl = allowModelDelete && model && !loading && !adapter;

  let content: ReactNode;
  if (loading) {
    content = (
      <Stack className="overflow-auto">
        <Block padding="4">
          <Loading />
        </Block>
      </Stack>
    );
  } else if (!model) {
    content = (
      <Stack className="overflow-auto">
        <Block padding="4">
          <Empty
            title="Awaiting Model Selection"
            description="Select a base model to get started"
          />
        </Block>
      </Stack>
    );
  } else if (selectedTab === 'model-details') {
    content = (
      <Stack className="overflow-auto">
        <Block padding="4">
          <ModelDetailOverview model={model} status={deployment?.status} {...overviewProps} />
        </Block>
        <ModelParametersAccordion
          model={model}
          adapter={adapter}
          deployment={deployment}
          artifactData={artifactData}
          showCustomizationDetails={showCustomizationDetails}
          customizationJobId={customizationJobId}
        />
      </Stack>
    );
  } else {
    const usedModelName = adapter?.name ?? model.name;
    const workspace = model.workspace;

    // When chatting with an adapter, route through the provider proxy which
    // forwards the request body as-is (preserving the adapter name in the
    // `model` field). The model-entity proxy would overwrite it with the
    // base model's served_model_name.
    let adapterBaseURL: string | undefined;
    if (adapter && model.model_providers?.length) {
      const providerRef = model.model_providers[0];
      const providerName = providerRef.includes('/') ? providerRef.split('/').pop()! : providerRef;
      adapterBaseURL =
        PLATFORM_BASE_URL + getProviderProxyGetQueryKey(workspace, providerName, 'v1/')[0];
    }

    content = (
      <Block className="h-full min-h-0" padding="4">
        {isChatStatusLoading ? (
          <Loading />
        ) : (
          <ModelChat
            model={usedModelName}
            workspace={workspace}
            baseURL={adapterBaseURL}
            promptData={model.prompt}
            modelChatStatus={modelChatStatus}
          />
        )}
      </Block>
    );
  }

  return (
    <SidePanel
      open={open}
      onOpenChange={onOpenChange}
      slotHeading={adapter ? `${model?.name} / ${adapter.name}` : model?.name}
      bordered
      modal
      className="[&.nv-side-panel-content]:w-[600px] [&_.nv-side-panel-main]:gap-4 [&_.nv-side-panel-main]:p-0"
      slotFooter={
        showDeleteControl ? (
          <>
            <Flex justify="end" className="w-full px-4 pb-4">
              <Button color="danger" type="button" onClick={() => setDeleteModalOpen(true)}>
                Delete
              </Button>
            </Flex>
            <DeleteConfirmationModal
              open={deleteModalOpen}
              title={`Delete model: ${model.name}`}
              description="This permanently removes the model entity from the workspace. Related deployments and resources may be affected."
              confirmationText={model.name}
              simpleConfirm
              successText={`Successfully deleted model ${model.name}`}
              errorText="Failed to delete the model. Try again or check your permissions."
              onClose={() => setDeleteModalOpen(false)}
              onDelete={handleDeleteModel}
            />
          </>
        ) : null
      }
      {...attributes?.SidePanel}
    >
      <Block className="w-full px-4">
        <SegmentedControl
          className="[&.nv-segmented-control-root]:mt-4 w-full!"
          value={selectedTab}
          items={tabItems}
          onValueChange={handleTabChange}
          {...attributes?.SegmentedControl}
        />
      </Block>
      {content}
    </SidePanel>
  );
};
