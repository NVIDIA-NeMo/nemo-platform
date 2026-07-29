// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RailsConfigDataOutput, RailsOutput } from '@nemo/sdk/generated/platform/schema';
import {
  AccordionContent,
  AccordionItem,
  AccordionRoot,
  AccordionTrigger,
  Badge,
  Flex,
  Panel,
  Text,
} from '@nvidia/foundations-react-core';
import {
  EmptyText,
  FieldList,
  ScopeBadges,
} from '@studio/routes/guardrails/GuardrailConfigTab/configPrimitives';
import {
  detectorMeta,
  deriveScopes,
  listConfiguredDetectors,
  summarizeDetector,
} from '@studio/routes/guardrails/GuardrailConfigTab/detectors';
import type { DetectorKey } from '@studio/routes/guardrails/GuardrailConfigTab/types';
import { ScanSearch } from 'lucide-react';
import type { FC } from 'react';

export const DetectorsSection: FC<{ rails: RailsOutput | undefined }> = ({ rails }) => {
  const detectors = listConfiguredDetectors(rails);
  const config: RailsConfigDataOutput = rails?.config ?? {};

  return (
    <Panel slotHeading="Detectors" slotIcon={<ScanSearch />} elevation="high" density="compact">
      {detectors.length === 0 ? (
        <EmptyText>No detectors configured.</EmptyText>
      ) : (
        <AccordionRoot multiple>
          {detectors.map((key) => {
            const meta = detectorMeta(key);
            const scopes = deriveScopes(rails, key);
            const fields = summarizeDetector(config[key as DetectorKey]);
            return (
              <AccordionItem key={key} value={key}>
                <AccordionTrigger>
                  <Flex align="center" justify="between" gap="density-md" className="w-full">
                    <Flex align="center" gap="density-sm" wrap="wrap">
                      <Text kind="label/bold/md">{meta.label}</Text>
                      <Badge color={meta.firstParty ? 'green' : 'gray'} kind="outline">
                        {meta.firstParty ? 'NVIDIA' : 'Third-party'}
                      </Badge>
                    </Flex>
                    <ScopeBadges scopes={scopes} />
                  </Flex>
                </AccordionTrigger>
                <AccordionContent>
                  {fields.length ? (
                    <FieldList fields={fields} />
                  ) : (
                    <EmptyText>Enabled with default settings.</EmptyText>
                  )}
                </AccordionContent>
              </AccordionItem>
            );
          })}
        </AccordionRoot>
      )}
    </Panel>
  );
};
