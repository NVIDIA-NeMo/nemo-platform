// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { IntakeTraceDetailView } from '@nemo/studio-plugins-example/intake-trace-detail-agent00/IntakeTraceDetailView';
import { overrideView, type StudioPlugin } from '@studio/plugins/types';

/**
 * Intake trace detail view override for the `agent00` workspace. Forked from
 * `intake-trace-detail` so agent00 can diverge without affecting `default`.
 */
export const intakeTraceDetailAgent00Plugin: StudioPlugin = {
  id: 'intake-trace-detail-agent00',
  name: 'Intake Trace Detail (agent00)',
  description: 'View override for the intake trace detail page in the agent00 workspace.',
  workspaces: ['agent00'],
  contributions: [],
  viewOverrides: [
    overrideView({
      viewId: 'intake.trace.detail',
      id: 'intake-trace-detail-agent00:view',
      render: IntakeTraceDetailView,
    }),
  ],
};
