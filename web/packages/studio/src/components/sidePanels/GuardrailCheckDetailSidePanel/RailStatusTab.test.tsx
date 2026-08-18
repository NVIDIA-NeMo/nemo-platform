// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RailsConfig } from '@nemo/sdk/generated/platform/schema';
import { RailStatusTab } from '@studio/components/sidePanels/GuardrailCheckDetailSidePanel/RailStatusTab';
import { render, screen } from '@testing-library/react';

/**
 * An unrecognized `rails.config` key humanizes to the same text as a flow of
 * that name. Deduping is by id, so both survive — and the label stops working.
 */
const COLLIDING_LABELS = {
  rails: {
    input: { flows: ['Acme Guard'] },
    config: { acme_guard: {} },
  },
} as unknown as RailsConfig;

describe('RailStatusTab', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('keys guardrail rows so two sharing a label do not collide', () => {
    const errors = vi.spyOn(console, 'error').mockImplementation(() => {});

    render(<RailStatusTab latestRun={undefined} configData={COLLIDING_LABELS} />);

    // Both rows render: they are distinct guardrails that happen to read alike.
    expect(screen.getAllByText('Acme Guard')).toHaveLength(2);

    const duplicateKeyWarnings = errors.mock.calls
      .map((call) => call.map(String).join(' '))
      .filter((message) => message.includes('same key'));
    expect(duplicateKeyWarnings).toEqual([]);
  });

  it('lists the config coverage a check with no runs has never exercised', () => {
    render(<RailStatusTab latestRun={undefined} configData={COLLIDING_LABELS} />);

    expect(screen.getByText('No runs yet.')).toBeInTheDocument();
    expect(screen.getByText('Activated Guardrails')).toBeInTheDocument();
  });

  // The config that produced a run may have been edited since — or, for a draft, never saved.
  it("prefers the run's own coverage snapshot over the current config", () => {
    render(
      <RailStatusTab
        latestRun={{
          run_at: '2026-04-12T11:05:00.000Z',
          status: 'success',
          rails_status: {},
          is_draft: true,
          activated_guardrails: [{ id: 'jailbreak', label: 'Jailbreak Detection', active: true }],
        }}
        configData={COLLIDING_LABELS}
      />
    );

    expect(screen.getByText('Jailbreak Detection')).toBeInTheDocument();
    expect(screen.queryByText('Acme Guard')).not.toBeInTheDocument();
  });

  it('falls back to the current config for a run recorded before snapshots existed', () => {
    render(
      <RailStatusTab
        latestRun={{ run_at: '2026-04-12T11:05:00.000Z', status: 'success', rails_status: {} }}
        configData={COLLIDING_LABELS}
      />
    );

    expect(screen.getAllByText('Acme Guard')).toHaveLength(2);
  });
});
