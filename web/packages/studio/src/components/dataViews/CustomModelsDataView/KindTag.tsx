// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { FinetuningType } from '@nemo/sdk/generated/platform/schema';
import { Group, Tag } from '@nvidia/foundations-react-core';
import { formatFinetuningType } from '@studio/util/customizations';
import type { FC } from 'react';

/** Training sub-type for display (sft, distillation, dpo, grpo). */
export const TrainingType = {
  sft: 'sft',
  distillation: 'distillation',
  dpo: 'dpo',
  grpo: 'grpo',
} as const;
export type TrainingType = (typeof TrainingType)[keyof typeof TrainingType];

const TRAINING_TYPE_LABELS: Record<TrainingType, string> = {
  [TrainingType.sft]: 'SFT',
  [TrainingType.distillation]: 'Distillation',
  [TrainingType.dpo]: 'DPO',
  [TrainingType.grpo]: 'GRPO',
};

export type KindTagProps = {
  finetuningType: FinetuningType;
  trainingType?: TrainingType;
  onClick: (finetuningType: FinetuningType) => void;
};

/**
 * Props for the KindTag component.
 * @property finetuningType - The main finetuning type.
 * @property trainingType - Optional sub-type of finetuning.
 * @property onClick - Handler called when tag is clicked, receives finetuning type.
 */
export const KindTag: FC<KindTagProps> = ({ finetuningType, trainingType, onClick }) => {
  // If training_type is provided, group the finetuning type and training type together
  if (trainingType) {
    return (
      <Group>
        <Tag kind="solid" color="purple" density="compact" onClick={() => onClick(finetuningType)}>
          {formatFinetuningType(finetuningType)}
        </Tag>
        <Tag kind="solid" color="purple" density="compact" onClick={() => onClick(finetuningType)}>
          {TRAINING_TYPE_LABELS[trainingType]}
        </Tag>
      </Group>
    );
  }

  // If training_type is not provided, show only the finetuning type
  return (
    <Tag kind="solid" color="green" density="compact" onClick={() => onClick(finetuningType)}>
      {formatFinetuningType(finetuningType)}
    </Tag>
  );
};
