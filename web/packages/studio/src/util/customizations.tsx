// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { formatFinetuningType } from '@nemo/common/src/utils/formatters';
import type { PlatformJobStatus } from '@nemo/sdk/generated/platform/schema';
import {
  isAutomodelJob,
  isUnslothJob,
  type CustomizationJob,
  type CustomizationJobStatusDetails,
} from '@nemo/sdk/vendored/customizer/schema';
import { Badge } from '@nvidia/foundations-react-core';
import { getTextWithCount } from '@studio/util/strings';
import { Circle /* TODO: replace with a proper icon (was Circle) */, Gpu } from 'lucide-react';
import { ReactNode } from 'react';

export { formatFinetuningType };

export type FileType = 'training' | 'testing' | 'validation';

/** Training/finetuning type for display (e.g. training.training_type / training.finetuning_type). */
export const getFormattedTrainingType = (type?: string) => {
  if (type === undefined) {
    return '';
  }
  switch (type) {
    case 'lora': {
      return 'LoRA';
    }
    case 'lora_merged': {
      return 'LoRA (merged)';
    }
    case 'all_weights': {
      return 'All Weights';
    }
    case 'sft': {
      return 'SFT';
    }
    case 'distillation': {
      return 'Distillation';
    }
    default: {
      return type;
    }
  }
};

/**
 * Returns the given status formatted in title case. For example, DEPLOYMENT_IN_PROGRESS returns
 * 'Deployment In Progress', optionally with the progress percentage.
 */
export const getFormattedCustomizationStatus = (
  status?: PlatformJobStatus | string,
  progressPercent?: number
) => {
  let statusText = '';

  if (status) {
    statusText = status
      .split('_')
      .map((word: string) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
      .join(' ');
  }

  if (progressPercent !== undefined) {
    statusText += ` (${Math.floor(progressPercent)}%)`;
  }

  return statusText;
};

/**
 * Returns the base model reference for a customization job. Automodel stores it as a string;
 * unsloth stores it as a `ModelLoadSpec` whose `name` is the reference.
 */
export const getBaseModel = (customizationJob?: CustomizationJob): string => {
  if (!customizationJob) {
    return '';
  }
  if (isUnslothJob(customizationJob)) {
    return customizationJob.spec.model.name ?? '';
  }
  if (isAutomodelJob(customizationJob)) {
    return customizationJob.spec.model ?? '';
  }
  return '';
};

/**
 * Returns the training dataset URI for a customization job. Automodel stores it under
 * `dataset.training`; unsloth stores it under `dataset.path`.
 */
export const getDatasetUri = (customizationJob?: CustomizationJob): string => {
  if (!customizationJob) {
    return '';
  }
  if (isAutomodelJob(customizationJob)) {
    return customizationJob.spec.dataset.training ?? '';
  }
  if (isUnslothJob(customizationJob)) {
    return customizationJob.spec.dataset.path ?? '';
  }
  return '';
};

/**
 * Effective training batch size, used to compute the loss-chart x-axis. Automodel uses
 * `batch.global_batch_size`; unsloth uses `batch.per_device_train_batch_size`.
 */
export const getTrainingBatchSize = (customizationJob?: CustomizationJob): number => {
  if (!customizationJob) {
    return 0;
  }
  if (isAutomodelJob(customizationJob)) {
    return customizationJob.spec.batch.global_batch_size ?? 0;
  }
  if (isUnslothJob(customizationJob)) {
    return customizationJob.spec.batch.per_device_train_batch_size ?? 0;
  }
  return 0;
};

/** Log entry in customization job status_details.status_logs */
interface StatusDetails {
  message?: string;
  detail?: string;
}

/**
 * Returns the error message of the first failure log from a customization job's status details.
 */
export const getFailureMessage = (statusDetails: CustomizationJobStatusDetails): string => {
  const logs: StatusDetails[] = (statusDetails.status_logs as StatusDetails[]) || [];
  const hasFailure = logs.find((log) => log.message?.includes('Failed'));
  if (hasFailure) {
    return logs.map((log) => log.detail || '').join('\n');
  }
  return '';
};

export const getProgressLogs = (statusDetails: CustomizationJobStatusDetails): StatusDetails[] => {
  const logs = (statusDetails.status_logs as StatusDetails[]) || [];
  return logs;
};

/**
 * Returns a string that represents the number of epochs completed by the given customization.
 */
export const getCustomizationTrainingProgress = (customization: CustomizationJob) => {
  if (!customization.status_details) {
    return '';
  }

  const epochs = customization.spec?.schedule?.epochs;

  const { epoch, percentage_done: percentageDone } = customization.status_details || {};

  if (epoch == null && percentageDone == null) {
    return '';
  }

  return `${epoch ?? 0}/${epochs ?? '?'} (${Math.floor(Number(percentageDone) || 0)}%)`;
};

const badge = (key: string, icon: ReactNode, label: string): ReactNode => (
  <Badge key={key} color="gray" kind="solid">
    {icon}
    {label}
  </Badge>
);

/**
 * Compute-configuration badges for a customization job. Automodel exposes distributed-training
 * `parallelism`; unsloth exposes single-node `hardware` (GPU list + precision).
 */
export const getTrainingOptionBadges = (job: CustomizationJob | null | undefined): ReactNode[] => {
  if (!job) return [];

  if (isAutomodelJob(job)) {
    const p = job.spec.parallelism;
    const badges: ReactNode[] = [
      badge('num_gpus_per_node', <Gpu />, getTextWithCount('GPU', p.num_gpus_per_node)),
      badge('num_nodes', <Circle />, getTextWithCount('Node', p.num_nodes)),
      badge(
        'tensor_parallel_size',
        <Gpu />,
        getTextWithCount('Tensor Parallel', p.tensor_parallel_size)
      ),
    ];
    if (p.sequence_parallel) {
      badges.push(badge('sequence_parallel', undefined, 'Sequence Parallel'));
    }
    return badges;
  }

  if (isUnslothJob(job)) {
    const { gpus, precision } = job.spec.hardware;
    const badges: ReactNode[] = [];
    if (gpus) {
      const gpuCount = gpus.split(',').filter(Boolean).length;
      badges.push(badge('gpus', <Gpu />, getTextWithCount('GPU', gpuCount)));
    }
    badges.push(badge('precision', undefined, `Precision: ${precision}`));
    return badges;
  }

  return [];
};

/**
 * The number of steps completed during training.
 * Used for showing a max x-axis value in the loss line chart.
 */
interface GetCustomizationTrainingStepsParams {
  epochs: number;
  trainingRecords: number;
  batchSize: number;
  hasValidationDataset?: boolean;
}
export const getCustomizationTrainingSteps = ({
  epochs,
  trainingRecords,
  batchSize,
  hasValidationDataset,
}: GetCustomizationTrainingStepsParams): number => {
  if (epochs === 0 || batchSize === 0 || trainingRecords === 0) {
    return 0;
  }
  if (hasValidationDataset) {
    // When both training and validation datasets are used
    return epochs * Math.ceil(trainingRecords / batchSize);
  } else {
    // When only training dataset is used (90% split for training)
    return epochs * Math.ceil(Math.ceil(trainingRecords * 0.9) / batchSize);
  }
};
