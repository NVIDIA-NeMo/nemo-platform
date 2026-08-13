// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RunRecord } from '@studio/api/guardrail-checks/types';
import { RunHistoryTab } from '@studio/components/sidePanels/GuardrailCheckDetailSidePanel/RunHistoryTab';
import { render, screen } from '@testing-library/react';

const run = (overrides: Partial<RunRecord>): RunRecord => ({
  run_at: '2026-04-12T11:05:00.000Z',
  status: 'success',
  rails_status: {},
  ...overrides,
});

describe('RunHistoryTab', () => {
  it('labels a saved run with the config version it ran against', () => {
    render(<RunHistoryTab runs={[run({ config_version: 3 })]} />);

    expect(screen.getByText('v3')).toBeInTheDocument();
    expect(screen.queryByText('Draft')).not.toBeInTheDocument();
  });

  it('marks a draft run instead of showing a version', () => {
    render(<RunHistoryTab runs={[run({ is_draft: true })]} />);

    expect(screen.getByText('Draft')).toBeInTheDocument();
    expect(screen.queryByText(/^v\d+$/)).not.toBeInTheDocument();
  });

  // Records written before either field existed must still render.
  it('shows no origin badge for a record carrying neither field', () => {
    render(<RunHistoryTab runs={[run({ run_at: '2026-04-12T11:06:00.000Z' })]} />);

    expect(screen.queryByText('Draft')).not.toBeInTheDocument();
    expect(screen.queryByText(/^v\d+$/)).not.toBeInTheDocument();
  });
});
