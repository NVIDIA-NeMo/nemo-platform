// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RailsConfigOutput } from '@nemo/sdk/generated/platform/schema';
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
} as unknown as RailsConfigOutput;

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
});
