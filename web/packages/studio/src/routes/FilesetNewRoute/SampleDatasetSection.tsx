// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Badge, Block, Card, Flex, Grid, GridItem, Text } from '@nvidia/foundations-react-core';
import { SAMPLE_DATASETS, SampleDataset } from '@studio/constants/sampleDatasets';
import { FileCheck } from 'lucide-react';
import { FC } from 'react';

interface SampleDatasetSectionProps {
  selectedSampleDataset: SampleDataset;
  onSelectSample: (dataset: SampleDataset) => void;
}

export const SampleDatasetSection: FC<SampleDatasetSectionProps> = ({
  selectedSampleDataset,
  onSelectSample,
}) => {
  return (
    <>
      <Block>
        <Text kind="body/regular/md" className="block">
          Choose from the following pre-configured sample datasets.
        </Text>
      </Block>
      <Grid gap="density-md" cols={2}>
        {SAMPLE_DATASETS.map((dataset) => (
          <GridItem key={dataset.id}>
            <Card
              interactive
              selected={selectedSampleDataset.id === dataset.id}
              onClick={() => onSelectSample(dataset)}
              className="cursor-pointer shadow-none!"
              slotHeader={
                <Badge kind="solid" color="purple">
                  <FileCheck />
                  Sample Dataset
                </Badge>
              }
            >
              <Flex gap="density-sm" direction="col">
                <Text kind="label/bold/md">{dataset.name}</Text>
                <Text kind="body/regular/md">{dataset.description}</Text>
              </Flex>
            </Card>
          </GridItem>
        ))}
      </Grid>
    </>
  );
};
