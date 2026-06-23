// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { SubmitEvaluationModal } from '@studio/routes/agents/AgentEvaluationsRoute/components/SubmitEvaluationModal';
import { EVAL_CONFIG_FILESET_HELP_TEXT } from '@studio/routes/agents/AgentSuggestionsRoute/constants';
import { renderRoute, screen } from '@studio/tests/util/render';
import userEvent from '@testing-library/user-event';

describe('SubmitEvaluationModal', () => {
  it('explains the required config format when fileset mode is selected', async () => {
    const user = userEvent.setup();

    renderRoute(
      <SubmitEvaluationModal open onClose={vi.fn()} workspace="default" agent="react-agent" />
    );

    expect(screen.queryByText(EVAL_CONFIG_FILESET_HELP_TEXT)).not.toBeInTheDocument();

    await user.click(
      screen.getByRole('radio', { name: 'Select or upload a config file from a fileset' })
    );

    expect(screen.getByText(EVAL_CONFIG_FILESET_HELP_TEXT)).toBeInTheDocument();
  });
});
