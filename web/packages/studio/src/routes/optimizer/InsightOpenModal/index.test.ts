// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { buildOptimizerExperimentCommand } from '@studio/routes/optimizer/InsightOpenModal/command';

describe('buildOptimizerExperimentCommand', () => {
  it('uses the optimizer experiment contract and quotes the insight and workspace', () => {
    const command = buildOptimizerExperimentCommand("insight-'quoted", "workspace-'quoted");

    expect(command).toBe(
      'nemo optimizer experiment \\\n' +
        "  --insight 'insight-'\\''quoted' \\\n" +
        '  --train-dataset "<train-dataset-path>" \\\n' +
        '  --validation-dataset "<validation-dataset-path>" \\\n' +
        "  --workspace 'workspace-'\\''quoted' \\\n" +
        '  --task-template "<task-template-path>"'
    );
  });
});
