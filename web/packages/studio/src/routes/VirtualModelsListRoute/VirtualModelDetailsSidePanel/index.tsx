// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { KVPair } from '@nemo/common/src/components/KVPair';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import type { MiddlewareCall, VirtualModel } from '@nemo/sdk/generated/platform/schema';
import {
  Block,
  Flex,
  SegmentedControl,
  SidePanel,
  Stack,
  Text,
} from '@nvidia/foundations-react-core';
import { DEFAULT_INFERENCE_PARAMS, type InferenceParams } from '@studio/components/chat/params';
import { ParamsPopover } from '@studio/components/chat/ParamsPopover';
import { ModelChat } from '@studio/components/ModelChat';
import { type FC, useMemo, useState } from 'react';

const MiddlewareCallView: FC<{ call: MiddlewareCall }> = ({ call }) => (
  <Block className="rounded-lg border border-base bg-surface-raised p-density-md">
    <Stack className="gap-density-sm">
      <KVPair label="Plugin" orientation="horizontal" size="narrow" value={call.name} />
      <KVPair label="Config type" orientation="horizontal" size="narrow" value={call.config_type} />
      {call.config_id ? (
        <KVPair
          label="Config ref"
          orientation="horizontal"
          size="narrow"
          truncate={false}
          value={call.config_id}
        />
      ) : null}
      {call.config && Object.keys(call.config).length > 0 ? (
        <Stack className="gap-density-xs">
          <Text kind="label/regular/sm" className="text-secondary">
            Config
          </Text>
          <pre className="overflow-auto whitespace-pre-wrap rounded bg-surface p-density-sm text-sm">
            {JSON.stringify(call.config, null, 2)}
          </pre>
        </Stack>
      ) : null}
    </Stack>
  </Block>
);

const MiddlewarePipeline: FC<{ label: string; calls: MiddlewareCall[] | undefined }> = ({
  label,
  calls,
}) => (
  <Stack className="gap-density-sm">
    <Text kind="label/bold/sm">{label}</Text>
    {calls && calls.length > 0 ? (
      calls.map((call, index) => <MiddlewareCallView key={`${call.name}-${index}`} call={call} />)
    ) : (
      <Text kind="body/regular/sm" className="text-secondary">
        None
      </Text>
    )}
  </Stack>
);

export interface VirtualModelDetailsSidePanelProps {
  open: boolean;
  onClose: () => void;
  onTabChange: (tab: VirtualModelPanelTab) => void;
  tab: VirtualModelPanelTab;
  virtualModel: VirtualModel;
}

export type VirtualModelPanelTab = 'details' | 'chat';

export const VirtualModelDetailsSidePanel: FC<VirtualModelDetailsSidePanelProps> = ({
  open,
  onClose,
  onTabChange,
  tab,
  virtualModel,
}) => {
  const models = virtualModel.models ?? [];
  const virtualModelName = virtualModel.name ?? '';
  const virtualModelWorkspace = virtualModel.workspace ?? '';
  const [inferenceParams, setInferenceParams] = useState<InferenceParams>({
    ...DEFAULT_INFERENCE_PARAMS,
    max_tokens: 4096,
  });
  const tabItems = useMemo(
    () => [
      { value: 'details', children: 'Details' },
      { value: 'chat', children: 'Chat' },
    ],
    []
  );

  return (
    <SidePanel
      className="[&.nv-side-panel-content]:w-[600px] [&_.nv-side-panel-main]:gap-4 [&_.nv-side-panel-main]:p-0"
      bordered
      modal
      open={open}
      slotHeading={
        <Text className="min-w-0 truncate" kind="label/bold/lg" title={virtualModel.name}>
          {virtualModel.name}
        </Text>
      }
      onOpenChange={(nextOpen) => {
        if (!nextOpen) {
          onClose();
        }
      }}
    >
      <Block className="w-full px-4">
        <SegmentedControl
          className="[&.nv-segmented-control-root]:mt-4 w-full!"
          value={tab}
          items={tabItems}
          onValueChange={(value) => onTabChange(value as VirtualModelPanelTab)}
        />
      </Block>

      {tab === 'details' ? (
        <Stack className="min-h-0 flex-1 gap-density-lg overflow-auto px-4 pb-4">
          <Stack className="gap-density-md">
            <KVPair
              label="Created"
              orientation="horizontal"
              size="medium"
              value={
                virtualModel.created_at ? (
                  <RelativeTime datetime={virtualModel.created_at} focusableForTooltip={false} />
                ) : (
                  '—'
                )
              }
            />
            <KVPair
              label="Default model"
              orientation="horizontal"
              size="medium"
              truncate={false}
              value={virtualModel.default_model_entity || '—'}
            />
            <KVPair
              label="Autoprovisioned"
              orientation="horizontal"
              size="medium"
              value={virtualModel.autoprovisioned ? 'Yes' : 'No'}
            />
            {virtualModel.override_proxy ? (
              <KVPair
                label="Override proxy"
                orientation="horizontal"
                size="medium"
                truncate={false}
                value={virtualModel.override_proxy}
              />
            ) : null}
            <KVPair
              attributes={{ value: { className: 'whitespace-pre-wrap' } }}
              label="Models"
              orientation="horizontal"
              size="medium"
              truncate={false}
              value={
                models.length > 0
                  ? models
                      .map((m) => (m.backend_format ? `${m.model} (${m.backend_format})` : m.model))
                      .join('\n')
                  : '—'
              }
            />
          </Stack>

          <Stack className="gap-density-md">
            <Text kind="label/bold/md">Middleware</Text>
            <MiddlewarePipeline label="Request" calls={virtualModel.request_middleware} />
            <MiddlewarePipeline label="Response" calls={virtualModel.response_middleware} />
            <MiddlewarePipeline
              label="Post-response"
              calls={virtualModel.post_response_middleware}
            />
          </Stack>
        </Stack>
      ) : (
        <Stack className="min-h-0 flex-1">
          <Flex align="center" justify="end" className="shrink-0 border-b border-base px-4 pb-3">
            <ParamsPopover value={inferenceParams} onChange={setInferenceParams} />
          </Flex>
          <Block className="h-full min-h-0" padding="4">
            <ModelChat
              key={`${virtualModelWorkspace}/${virtualModelName}`}
              model={virtualModelName}
              workspace={virtualModelWorkspace}
              assistantName={virtualModelName}
              disabled={!virtualModelName || !virtualModelWorkspace}
              promptData={{ inference_params: inferenceParams }}
            />
          </Block>
        </Stack>
      )}
    </SidePanel>
  );
};
