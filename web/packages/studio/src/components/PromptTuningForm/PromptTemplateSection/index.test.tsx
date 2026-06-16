// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DEFAULT_PROMPT_TEMPLATE } from '@nemo/common/src/models/constants';
import { FormWrapper } from '@nemo/common/src/tests/formComponents';
import { AccordionRoot } from '@nvidia/foundations-react-core';
import { PromptTemplateSection } from '@studio/components/PromptTuningForm/PromptTemplateSection';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

describe('PromptTemplateSection', () => {
  it('resets the input when the Reset To Default is clicked', async () => {
    const user = userEvent.setup();

    render(
      <FormWrapper>
        <AccordionRoot defaultValue="system-prompt">
          <PromptTemplateSection />
        </AccordionRoot>
      </FormWrapper>
    );

    const promptTemplateInput = screen.getByRole('textbox');
    await user.type(promptTemplateInput, 'test prompt template');

    expect(promptTemplateInput).toHaveValue('test prompt template');

    const resetButton = screen.getByRole('button', { name: 'Reset Prompt' });
    await user.click(resetButton);

    expect(promptTemplateInput).toHaveValue(DEFAULT_PROMPT_TEMPLATE);
  });
});
