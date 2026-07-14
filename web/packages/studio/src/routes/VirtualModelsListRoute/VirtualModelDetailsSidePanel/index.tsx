// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { KVPair } from '@nemo/common/src/components/KVPair';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import type { MiddlewareCall, VirtualModel } from '@nemo/sdk/generated/platform/schema';
import { Block, SidePanel, Stack, Text } from '@nvidia/foundations-react-core';
import type { FC } from 'react';

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
  virtualModel: VirtualModel;
}

export const VirtualModelDetailsSidePanel: FC<VirtualModelDetailsSidePanelProps> = ({
  open,
  onClose,
  virtualModel,
}) => {
  const models = virtualModel.models ?? [];

  return (
    <SidePanel
      className="w-[600px]"
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
      <Stack className="min-h-0 flex-1 gap-density-lg overflow-auto">
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
          <MiddlewarePipeline label="Post-response" calls={virtualModel.post_response_middleware} />
        </Stack>
      </Stack>
    </SidePanel>
  );
};
