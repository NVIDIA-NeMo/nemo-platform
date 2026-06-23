// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { IntakeTraceDetailView } from '@nemo/studio-plugins-example/intake-trace-detail/IntakeTraceDetailView';
import { overrideView, type StudioPlugin } from '@studio/plugins/types';

/**
 * Replaces the intake trace detail page (`/workspaces/:workspace/intake/traces/:traceId`)
 * when the studio plugins flag is on. The view starts as a duplicate of the first-party
 * implementation so it can be customized without touching core routes.
 */
export const intakeTraceDetailPlugin: StudioPlugin = {
  id: 'intake-trace-detail',
  name: 'Intake Trace Detail',
  description: 'View override for the intake trace detail page.',
  workspaces: ['default'],
  contributions: [],
  viewOverrides: [
    overrideView({
      viewId: 'intake.trace.detail',
      id: 'intake-trace-detail:view',
      render: IntakeTraceDetailView,
    }),
  ],
};
