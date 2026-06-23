// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ApplyEvalConfigModal } from '@studio/routes/agents/AgentSuggestionsRoute/components/ApplyEvalConfigModal';
import { EVAL_CONFIG_FILESET_HELP_TEXT } from '@studio/routes/agents/AgentSuggestionsRoute/constants';
import { renderRoute, screen } from '@studio/tests/util/render';
import userEvent from '@testing-library/user-event';

describe('ApplyEvalConfigModal', () => {
  it('explains the required config format when fileset mode is selected', async () => {
    const user = userEvent.setup();

    renderRoute(
      <ApplyEvalConfigModal
        open
        onClose={vi.fn()}
        workspace="default"
        suggestionTitle="Validate smaller model"
        onConfirm={vi.fn()}
      />
    );

    expect(screen.queryByText(EVAL_CONFIG_FILESET_HELP_TEXT)).not.toBeInTheDocument();

    await user.click(
      screen.getByRole('radio', { name: 'Select or upload a config file from a fileset' })
    );

    expect(screen.getByText(EVAL_CONFIG_FILESET_HELP_TEXT)).toBeInTheDocument();
  });
});
