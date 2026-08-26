// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { CustomizationJobStatusDetails } from '@studio/util/customizationBackend';

export interface CustomizationMetricValue {
  step: number;
  value: number;
  epoch?: number;
}

/**
 * Keyed by the `<phase>_<name>` the callback reports. The two losses are named because the backend
 * always sends both keys; the rest depend on the algorithm and can carry a `/`, so they are indexed.
 */
export interface CustomizationMetricSeries {
  train_loss?: CustomizationMetricValue[];
  val_loss?: CustomizationMetricValue[];
  [name: string]: CustomizationMetricValue[] | undefined;
}

/**
 * Training-progress fields that get merged into status_details
 * once training callbacks start reporting.
 */
export interface CustomizationStatusDetailsWithMetrics extends CustomizationJobStatusDetails {
  metrics?: CustomizationMetricSeries;
}

export function hasMetrics(
  statusDetails: CustomizationJobStatusDetails | undefined
): statusDetails is CustomizationStatusDetailsWithMetrics {
  return statusDetails !== undefined && 'metrics' in statusDetails;
}

export interface CustomizationTrainingTelemetry {
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
