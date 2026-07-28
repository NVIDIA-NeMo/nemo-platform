// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

const shellQuote = (value: string): string => value.replace(/'/g, "'\\''");

export const buildOptimizerExperimentCommand = (insightId: string, workspace: string): string =>
  `nemo optimizer experiment \\\n` +
  `  --insight '${shellQuote(insightId)}' \\\n` +
  `  --train-dataset "<train-dataset-path>" \\\n` +
  `  --validation-dataset "<validation-dataset-path>" \\\n` +
  `  --workspace '${shellQuote(workspace)}' \\\n` +
  `  --task-template "<task-template-path>"`;
