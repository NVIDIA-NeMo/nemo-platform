// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { KVPair } from '@nemo/common/src/components/KVPair';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { Badge, Flex, Panel, Stack, Text } from '@nvidia/foundations-react-core';
import { countRails } from '@studio/components/dataViews/GuardrailsDataView/guardrailUtils';
import { BehaviorSection } from '@studio/routes/guardrails/GuardrailConfigTab/BehaviorSection';
import { listConfiguredDetectors } from '@studio/routes/guardrails/GuardrailConfigTab/detectors';
import { DetectorsSection } from '@studio/routes/guardrails/GuardrailConfigTab/DetectorsSection';
import { GeneralSection } from '@studio/routes/guardrails/GuardrailConfigTab/GeneralSection';
import { LlmSection } from '@studio/routes/guardrails/GuardrailConfigTab/LlmSection';
import { PipelineSection } from '@studio/routes/guardrails/GuardrailConfigTab/PipelineSection';
import { RawConfigSection } from '@studio/routes/guardrails/GuardrailConfigTab/RawConfigSection';
import {
  applyFormToConfig,
  type GuardrailFormValues,
} from '@studio/routes/guardrails/GuardrailForm/formModel';
import { useGuardrailForm } from '@studio/routes/guardrails/GuardrailForm/useGuardrailForm';
import { Shield } from 'lucide-react';
import type { FC } from 'react';
import { useFormContext, useWatch } from 'react-hook-form';

export const GuardrailConfigTab: FC = () => {
  const { config } = useGuardrailForm();
  const { control } = useFormContext<GuardrailFormValues>();
  // Fields all have string defaults, so watched values are never undefined at runtime.
  const values = useWatch({ control }) as GuardrailFormValues;

  // Read-only sections reflect live edits: server data with the form applied.
  const data = applyFormToConfig(config.data, values);
  const rails = data.rails;
  const modelCount = data.models?.length ?? 0;
  const railCount = countRails(data);
  const detectorCount = listConfiguredDetectors(rails).length;
  const passthrough = data.passthrough === true;

  return (
    <Stack className="gap-density-2xl">
      <GeneralSection />

      <Panel slotHeading="Overview" slotIcon={<Shield />} elevation="high" density="compact">
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
          <KVPair
            label="Models"
            orientation="horizontal"
            size="medium"
            value={String(modelCount)}
          />
          <KVPair label="Rails" orientation="horizontal" size="medium" value={String(railCount)} />
          <KVPair
            label="Detectors"
            orientation="horizontal"
            size="medium"
            value={String(detectorCount)}
          />
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
          {passthrough ? (
            <Flex align="center" gap="density-sm">
              <Badge color="yellow" kind="solid">
                Passthrough
              </Badge>
              <Text kind="body/regular/xs" className="text-text-secondary">
                The prompt passes through unaltered; rails observe but do not modify it.
              </Text>
            </Flex>
          ) : null}
        </Stack>
      </Panel>

      <PipelineSection rails={rails} />
      <DetectorsSection rails={rails} />
      <LlmSection data={data} />
      <BehaviorSection data={data} />
      <RawConfigSection data={data} />
    </Stack>
  );
};
