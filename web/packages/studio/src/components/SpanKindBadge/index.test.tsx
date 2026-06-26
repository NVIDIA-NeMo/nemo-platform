// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { SpanKindBadge } from '@studio/components/SpanKindBadge';
import { render, screen } from '@studio/tests/util/render';

describe('SpanKindBadge', () => {
  it.each([
    ['AGENT', 'Agent'],
    ['LLM', 'LLM'],
    ['TOOL', 'Tool'],
    ['EVALUATOR', 'Evaluator'],
    ['GUARDRAIL', 'Guardrail'],
  ] as const)('renders kind %s with label %s', (kind, label) => {
    render(<SpanKindBadge kind={kind} />);

    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it('falls back to Unknown for an unrecognized kind', () => {
    render(<SpanKindBadge kind="NOT_A_KIND" />);

    expect(screen.getByText('Unknown')).toBeInTheDocument();
  });

  it('falls back to Unknown when kind is undefined', () => {
    render(<SpanKindBadge kind={undefined} />);

    expect(screen.getByText('Unknown')).toBeInTheDocument();
  });
});
