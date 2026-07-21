// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RailsConfigOutput } from '@nemo/sdk/generated/platform/schema';
import { Badge, Flex, Panel, Stack, Text } from '@nvidia/foundations-react-core';
import { FieldList } from '@studio/routes/guardrails/GuardrailConfigTab/configPrimitives';
import type { Field } from '@studio/routes/guardrails/GuardrailConfigTab/types';
import { SlidersHorizontal } from 'lucide-react';
import type { FC } from 'react';

const behaviorFields = (data: RailsConfigOutput | undefined): Field[] => {
  const fields: Field[] = [];
  if (data?.passthrough != null) {
    fields.push({ label: 'Passthrough', value: data.passthrough ? 'On' : 'Off' });
  }
  if (data?.enable_rails_exceptions != null) {
    fields.push({
      label: 'Rails exceptions',
      value: data.enable_rails_exceptions ? 'Raised' : 'Return messages',
    });
  }
  if (data?.colang_version) fields.push({ label: 'Colang version', value: data.colang_version });
  if (data?.actions_server_url) {
    fields.push({ label: 'Actions server', value: data.actions_server_url });
  }
  return fields;
};

const tracingFields = (data: RailsConfigOutput | undefined): Field[] => {
  const tracing = data?.tracing;
  if (!tracing) return [];
  const fields: Field[] = [];
  if (tracing.enabled != null) {
    fields.push({ label: 'Tracing', value: tracing.enabled ? 'Enabled' : 'Disabled' });
  }
  if (tracing.span_format) fields.push({ label: 'Span format', value: tracing.span_format });
  if (tracing.adapters?.length) {
    fields.push({
      label: 'Adapters',
      value: tracing.adapters.map((adapter) => adapter.name ?? 'unnamed').join(', '),
    });
  }
  return fields;
};

const hasBehaviorContent = (data: RailsConfigOutput | undefined): boolean =>
  behaviorFields(data).length > 0 || Boolean(data?.tracing);

export const BehaviorSection: FC<{ data: RailsConfigOutput | undefined }> = ({ data }) => {
  if (!hasBehaviorContent(data)) return null;

  const captureEnabled = data?.tracing?.enable_content_capture === true;

  return (
    <Panel
      slotHeading="Behavior &amp; operations"
      slotIcon={<SlidersHorizontal />}
      elevation="high"
      density="compact"
    >
      <Stack gap="density-md">
        <FieldList fields={behaviorFields(data)} />
        <FieldList fields={tracingFields(data)} />
        {captureEnabled ? (
          <Flex align="center" gap="density-sm">
            <Badge color="yellow" kind="solid">
              Content capture on
            </Badge>
            <Text kind="body/regular/xs" className="text-text-secondary">
              Prompts and responses are recorded in traces and may include PII.
            </Text>
          </Flex>
        ) : null}
      </Stack>
    </Panel>
  );
};
