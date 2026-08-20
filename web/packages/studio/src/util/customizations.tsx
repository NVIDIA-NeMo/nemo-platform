// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { StatTileProps } from '@nemo/common/src/components/StatTile';
import { formatTimeInSeconds, utcToLocalDate } from '@nemo/common/src/utils/date';
import { formatFinetuningType } from '@nemo/common/src/utils/formatters';
import type { PlatformJobStatus } from '@nemo/sdk/generated/platform/schema';
import { Badge } from '@nvidia/foundations-react-core';
import type {
  CustomizationMetricValue,
  CustomizationStatusDetailsWithMetrics,
  CustomizationTrainingTelemetry,
} from '@studio/types/customization';
import {
  isAutomodelJob,
  isUnslothJob,
  type CustomizationJob,
  type CustomizationJobStatusDetails,
} from '@studio/util/customizationBackend';
import { formatElapsedTime } from '@studio/util/date';
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

export const getFinetuningType = (customizationJob?: CustomizationJob): string => {
  if (!customizationJob) {
    return '';
  }
  if (isAutomodelJob(customizationJob)) {
    return customizationJob.spec.training?.finetuning_type ?? '';
  }
  if (isUnslothJob(customizationJob)) {
    return customizationJob.spec.training?.finetuning_type ?? '';
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
    return customizationJob.spec.batch?.per_device_train_batch_size ?? 0;
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

const asFiniteNumber = (value: unknown): number | undefined =>
  typeof value === 'number' && Number.isFinite(value) ? value : undefined;

const asNonEmptyString = (value: unknown): string | undefined =>
  typeof value === 'string' && value.length > 0 ? value : undefined;

export const getTrainingTelemetry = (
  job: CustomizationJob | null | undefined
): CustomizationTrainingTelemetry => {
  const details = job?.status_details;
  if (!details) return {};
  return {
    phase: asNonEmptyString(details.phase),
    step: asFiniteNumber(details.step),
    maxSteps: asFiniteNumber(details.max_steps),
    numEpochs: asFiniteNumber(details.num_epochs),
    epoch: asFiniteNumber(details.epoch),
    trainLoss: asFiniteNumber(details.train_loss),
    valLoss: asFiniteNumber(details.val_loss),
    // `?? details.lr` reads jobs written before the phase prefix was applied to
    // every metric name. Those are already in the database and never change, so
    // without the fallback their Learning Rate and Gradient Norm render blank
    // forever. `train_loss` and `val_loss` need no equivalent -- they were
    // already spelled that way.
    learningRate: asFiniteNumber(details.train_lr ?? details.lr),
    gradNorm: asFiniteNumber(details.train_grad_norm ?? details.grad_norm),
    checkpointPath: asNonEmptyString(details.checkpoint_path),
  };
};

interface MetricSummary {
  final: number;
  deltaFromStart?: number;
}

const summarizeMetric = (series?: CustomizationMetricValue[]): MetricSummary | undefined => {
  if (!series?.length) return undefined;
  const final = series[series.length - 1].value;
  const deltaFromStart = series.length > 1 ? final - series[0].value : undefined;
  return { final, deltaFromStart };
};

/**
 * Past this magnitude `toFixed` produces a string long enough to distort the tile grid, so the
 * value switches to exponential. Diverged runs are exactly when these numbers get large.
 */
const EXPONENTIAL_ABOVE = 1e6;

/**
 * Longest phase label rendered before truncating. Known phases top out at "Processing
 * Checkpoint" (21 chars); this only bites on phases the backend adds later, which are
 * title-cased verbatim and otherwise unbounded.
 */
const MAX_PHASE_LENGTH = 22;

const truncatePhase = (phase: string): string =>
  phase.length > MAX_PHASE_LENGTH ? `${phase.slice(0, MAX_PHASE_LENGTH - 1)}…` : phase;

export const formatMetricValue = (value: number, decimals = 4): string =>
  Math.abs(value) >= EXPONENTIAL_ABOVE ? value.toExponential(2) : value.toFixed(decimals);

/** Compact past four digits so a long run's step count cannot widen the column. */
export const formatStepCount = (value: number): string =>
  Math.abs(value) >= 10_000
    ? new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 }).format(
        value
      )
    : value.toLocaleString();

const formatDeltaHint = (delta: number, decimals: number): string =>
  `${delta >= 0 ? '+' : ''}${formatMetricValue(delta, decimals)} from start`;

const NOT_AVAILABLE = '—';

const lossTile = (label: string, summary?: MetricSummary): StatTileProps => {
  if (!summary) {
    return { label, value: NOT_AVAILABLE };
  }
  return {
    label,
    value: formatMetricValue(summary.final),
    hint:
      summary.deltaFromStart !== undefined ? formatDeltaHint(summary.deltaFromStart, 4) : undefined,
    hintStatus:
      summary.deltaFromStart !== undefined
        ? summary.deltaFromStart < 0
          ? 'success'
          : 'error'
        : undefined,
  };
};

export const getTrainingProgressTiles = (
  telemetry: CustomizationTrainingTelemetry
): StatTileProps[] => [
  {
    label: 'Steps Completed',
    value:
      telemetry.step === undefined
        ? NOT_AVAILABLE
        : telemetry.maxSteps
          ? `${formatStepCount(telemetry.step)} / ${formatStepCount(telemetry.maxSteps)}`
          : formatStepCount(telemetry.step),
  },
  {
    label: 'Epochs Completed',
    value:
      telemetry.epoch === undefined
        ? NOT_AVAILABLE
        : telemetry.numEpochs
          ? `${telemetry.epoch} / ${telemetry.numEpochs}`
          : String(telemetry.epoch),
  },
];

export const getLossTiles = (
  statusDetails: CustomizationStatusDetailsWithMetrics | undefined,
  isTerminal = false
): StatTileProps[] => [
  lossTile(
    `${isTerminal ? 'Final' : 'Latest'} Training Loss`,
    summarizeMetric(statusDetails?.metrics?.train_loss)
  ),
  lossTile(
    `${isTerminal ? 'Final' : 'Latest'} Validation Loss`,
    summarizeMetric(statusDetails?.metrics?.val_loss)
  ),
];

const TRAINING_PHASE_LABELS: Record<string, string> = {
  compiling_config: 'Compiling Config',
  automodel_recipe_setup: 'Recipe Setup',
  training: 'Training',
  validation: 'Validation',
  checkpoint_saved: 'Checkpoint Saved',
  epoch_end: 'Epoch End',
  processing_checkpoint: 'Processing Checkpoint',
  completed: 'Completed',
};

export const formatTrainingPhase = (phase: string): string =>
  TRAINING_PHASE_LABELS[phase] ??
  phase
    .split('_')
    .map((word) => (word ? word.charAt(0).toUpperCase() + word.slice(1) : word))
    .join(' ');

export interface JobDurationStep {
  created_at: string;
  updated_at: string;
}

export const getJobStartDate = (steps: readonly JobDurationStep[] | undefined): Date | undefined =>
  steps?.length ? utcToLocalDate(steps[0].created_at) : undefined;

export const getJobDuration = (
  steps: readonly JobDurationStep[] | undefined,
  isTerminal: boolean,
  liveSeconds?: number
): string => {
  if (!isTerminal) {
    return formatTimeInSeconds(liveSeconds) || NOT_AVAILABLE;
  }

  if (!steps?.length) {
    return NOT_AVAILABLE;
  }

  const start = utcToLocalDate(steps[0].created_at);
  const end = utcToLocalDate(steps[steps.length - 1].updated_at);
  if (!start || !end || end.getTime() - start.getTime() < 1000) {
    return NOT_AVAILABLE;
  }
  return formatElapsedTime(start, end);
};

interface TrainingDiagnosticsContext {
  isTerminal: boolean;
  duration: string;
}

export const getTrainingDiagnosticsTiles = (
  telemetry: CustomizationTrainingTelemetry,
  statusDetails: CustomizationStatusDetailsWithMetrics | undefined,
  { isTerminal, duration }: TrainingDiagnosticsContext
): StatTileProps[] => {
  const trainLoss = summarizeMetric(statusDetails?.metrics?.train_loss);
  const valLoss = summarizeMetric(statusDetails?.metrics?.val_loss);

  return [
    {
      label: 'Learning Rate',
      value: telemetry.learningRate?.toExponential(2) ?? NOT_AVAILABLE,
      hint: 'at latest step',
    },
    {
      label: 'Gradient Norm',
      value:
        telemetry.gradNorm !== undefined ? formatMetricValue(telemetry.gradNorm) : NOT_AVAILABLE,
      hint: 'at latest step',
    },
    {
      label: 'Train/Val Gap',
      value:
        trainLoss && valLoss ? formatMetricValue(valLoss.final - trainLoss.final) : NOT_AVAILABLE,
      hint: 'validation - training',
    },
    isTerminal
      ? { label: 'Duration', value: duration, hint: 'total run time' }
      : {
          label: 'Phase',
          value: telemetry.phase
            ? truncatePhase(formatTrainingPhase(telemetry.phase))
            : NOT_AVAILABLE,
          hint: 'current stage',
        },
  ];
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
      badge('num_gpus_per_node', <Gpu />, getTextWithCount('GPU', p.num_gpus_per_node ?? 0)),
      badge('num_nodes', <Circle />, getTextWithCount('Node', p.num_nodes ?? 0)),
      badge(
        'tensor_parallel_size',
        <Gpu />,
        getTextWithCount('Tensor Parallel', p.tensor_parallel_size ?? 0)
      ),
    ];
    if (p.sequence_parallel) {
      badges.push(badge('sequence_parallel', undefined, 'Sequence Parallel'));
    }
    return badges;
  }

  if (isUnslothJob(job)) {
    const { gpus, precision } = job.spec.hardware ?? {};
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
