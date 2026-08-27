// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { GuardrailCheckEntity } from '@studio/api/guardrail-checks/types';
import { mockGuardrailChecks } from '@studio/mocks/handlers/guardrails';
import { GuardrailTestCard } from '@studio/routes/guardrails/GuardrailChecksTab/GuardrailTestCard';
import { render, screen } from '@studio/tests/util/render';

const [seedCheck] = mockGuardrailChecks;

const renderCard = (autoFocus: boolean, check: GuardrailCheckEntity = seedCheck!) =>
  render(
    <GuardrailTestCard
      check={check}
      index={0}
      workspace="default"
      registerFlush={() => {}}
      autoFocus={autoFocus}
    />
  );

describe('GuardrailTestCard', () => {
  // "Add Another Test" appends below the fold; the card it produced has to come to the user.
  it('focuses the first message body when it is the just-created card', () => {
    renderCard(true);

    expect(screen.getByTestId('guardrail-check-message-content')).toHaveFocus();
  });

  it('leaves focus alone for an existing card', () => {
    renderCard(false);

    expect(screen.getByTestId('guardrail-check-message-content')).not.toHaveFocus();
  });
});
