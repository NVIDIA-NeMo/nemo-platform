// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  Block,
  Button,
  Flex,
  Grid,
  GridItem,
  PageHeader,
  Stack,
  Text,
} from '@nvidia/foundations-react-core';
import { START_OPTIONS } from '@studio/components/CreateFilesetStart/constants';
import { StartOptionCard } from '@studio/components/CreateFilesetStart/StartOptionCard';
import { StartOptionDetail } from '@studio/components/CreateFilesetStart/StartOptionDetail';
import type {
  CreateFilesetStartProps,
  StartOptionId,
} from '@studio/components/CreateFilesetStart/types';
import { ArrowRight } from 'lucide-react';
import { useState, type FC } from 'react';

export const CreateFilesetStart: FC<CreateFilesetStartProps> = ({ onContinue }) => {
  const [selectedId, setSelectedId] = useState<StartOptionId | null>(null);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null);
  const selectedOption = START_OPTIONS.find((option) => option.id === selectedId) ?? null;

  const selectOption = (optionId: StartOptionId) => {
    setSelectedId(optionId);
    setSelectedTemplateId(null);
  };

  // Ready to continue once a tile is chosen — and, for "template", a template card too.
  const canContinue =
    selectedOption !== null && (selectedOption.id !== 'template' || selectedTemplateId !== null);

  const handleContinue = () => {
    if (!selectedOption) return;
    if (selectedOption.id === 'template' && selectedTemplateId) {
      onContinue(selectedOption.id, selectedTemplateId);
    } else {
      onContinue(selectedOption.id);
    }
  };

  return (
    <Stack className="h-full">
      <Block className="flex-1 overflow-auto">
        <Stack gap="density-2xl" padding="density-2xl">
          <PageHeader
            slotHeading="Create a fileset"
            slotDescription="Generate synthetic data visually — no JSON to write. Start from a template, clone a fileset you already built, or describe what you need and let AI lay out the columns."
          />

          <Stack gap="density-md">
            <Text kind="label/bold/sm" className="text-secondary">
              How do you want to start?
            </Text>
            <Grid colMinWidth="200px" gap="density-md">
              {START_OPTIONS.map((option) => (
                <GridItem key={option.id}>
                  <StartOptionCard
                    option={option}
                    selected={selectedId === option.id}
                    onSelect={() => selectOption(option.id)}
                  />
                </GridItem>
              ))}
            </Grid>
          </Stack>

          {selectedOption ? (
            <StartOptionDetail
              option={selectedOption}
              selectedTemplateId={selectedTemplateId}
              onSelectTemplate={setSelectedTemplateId}
            />
          ) : null}
        </Stack>
      </Block>

      {canContinue ? (
        <Flex
          align="center"
          justify="end"
          className="shrink-0 gap-4 border-t border-base bg-surface-base px-10 py-4"
        >
          <Button color="brand" kind="primary" onClick={handleContinue}>
            Continue
            <ArrowRight size={16} aria-hidden />
          </Button>
        </Flex>
      ) : null}
    </Stack>
  );
};
