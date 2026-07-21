// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RailsOutput } from '@nemo/sdk/generated/platform/schema';
import { DetectorsSection } from '@studio/routes/guardrails/GuardrailConfigTab/DetectorsSection';
import { PipelineSection } from '@studio/routes/guardrails/GuardrailConfigTab/PipelineSection';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { render, screen } from '@testing-library/react';

const rails: RailsOutput = {
  config: {
    content_safety: { reasoning: { enabled: true } },
    gliner: { input: { entities: ['email'] }, output: { entities: ['ssn'] } },
    clavata: { server_endpoint: 'https://example.com' },
  },
  input: {
    parallel: true,
    flows: ['content safety check input $model=content_safety', 'my custom rail'],
  },
  output: { flows: ['content safety check output $model=content_safety'] },
};

describe('PipelineSection', () => {
  it('renders core stages, friendly + raw flow names, and empty states', () => {
    render(
      <TestProviders>
        <PipelineSection rails={rails} />
      </TestProviders>
    );

    // Core stages are always present.
    expect(screen.getByText('Input rails')).toBeInTheDocument();
    expect(screen.getByText('Retrieval rails')).toBeInTheDocument();
    expect(screen.getByText('Output rails')).toBeInTheDocument();

    // Recognized flow gets a friendly label; the raw string is still shown.
    expect(screen.getAllByText('Content Safety').length).toBeGreaterThan(0);
    expect(
      screen.getByText('content safety check input $model=content_safety')
    ).toBeInTheDocument();

    // Custom/unrecognized flow renders verbatim.
    expect(screen.getByText('my custom rail')).toBeInTheDocument();

    // Empty core stage advertises the gap.
    expect(screen.getAllByText('No rails configured.').length).toBeGreaterThan(0);
  });
});

describe('DetectorsSection', () => {
  it('lists configured detectors with provenance and scope', () => {
    render(
      <TestProviders>
        <DetectorsSection rails={rails} />
      </TestProviders>
    );

    expect(screen.getByText('Content Safety')).toBeInTheDocument();
    expect(screen.getByText('PII — GLiNER')).toBeInTheDocument();
    expect(screen.getByText('Clavata')).toBeInTheDocument();
    // First-party vs third-party provenance badges.
    expect(screen.getAllByText('NVIDIA').length).toBeGreaterThan(0);
    expect(screen.getByText('Third-party')).toBeInTheDocument();
  });
});
