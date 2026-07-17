// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { CustomizationJobStatusDetails } from '@studio/util/customizationBackend';

export interface CustomizationMetricValue {
  step: number;
  value: number;
  epoch?: number;
}

/**
 * Training-progress fields that get merged into status_details
 * once training callbacks start reporting.
 */
export interface CustomizationStatusDetailsWithMetrics extends CustomizationJobStatusDetails {
  metrics?: {
    train_loss?: CustomizationMetricValue[];
    val_loss?: CustomizationMetricValue[];
  };
}

export function hasMetrics(
  statusDetails: CustomizationJobStatusDetails | undefined
): statusDetails is CustomizationStatusDetailsWithMetrics {
  return statusDetails !== undefined && 'metrics' in statusDetails;
}

/**
 * Live per-step training telemetry the backend streams into the free-form `status_details` dict.
 * Every field is optional: the wire type is `Record<string, unknown>` and a given trainer may omit
 * any key (e.g. `lr`/`grad_norm` arrive absent when the underlying trainer doesn't report them).
 */
export interface CustomizationTrainingTelemetry {
  /** Lifecycle phase, e.g. 'training', 'validation', 'checkpoint_saved', 'completed'. */
  phase?: string;
  step?: number;
  maxSteps?: number;
  numEpochs?: number;
  epoch?: number;
  trainLoss?: number;
  valLoss?: number;
  learningRate?: number;
  gradNorm?: number;
  checkpointPath?: string;
}
