// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { SuiteRow } from '@iron-swarm/components/hitlTypes';
import type {
  AttackIntensity,
  BenignSource,
  ReplaySource,
} from '@iron-swarm/routes/IronSwarmManifestDetailRoute/types';

export const INTENSITY_LABEL: Record<AttackIntensity, string> = {
  light: 'Light',
  standard: 'Standard',
  thorough: 'Thorough',
};

export const REPLAY_SOURCE_LABEL: Record<ReplaySource, string> = {
  last: 'Last run',
  upload: 'Upload hitlog',
};

export const BENIGN_SOURCE_LABEL: Record<BenignSource, string> = {
  manifest: 'Manifest default',
  upload: 'Upload CSV',
};

// iron-swarm's benign requests.csv column order (mirrors jobs/benign_suite.py SUITE_FIELDS).
export const CSV_FIELDS = [
  'tool',
  'payload',
  'label',
  'rationale',
  'persona',
] as const satisfies readonly (keyof SuiteRow)[];
