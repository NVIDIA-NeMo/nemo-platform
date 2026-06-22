// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { getEntityReference } from '@nemo/common/src/namedEntity';
import { entityStoreBaseModel1 } from '@studio/mocks/entity-store/models';
import { render, screen } from '@studio/tests/util/render';

import { ModelChat } from '.';

vi.mock('@nemo/common/src/hooks/useChatCompletion', () => ({
  useChatCompletion: () => ({
    mutateAsync: vi.fn(),
  }),
}));

describe('ModelChat', () => {
  const modelName = getEntityReference(entityStoreBaseModel1);

  it('shows the model name in the composer placeholder', async () => {
    render(<ModelChat model={modelName} />);

    expect(await screen.findByPlaceholderText(`Message ${modelName}`)).toBeInTheDocument();
  });

  it('renders provided initialMessages in the thread', async () => {
    render(
      <ModelChat
        model={modelName}
        initialMessages={[
          { role: 'user', content: 'Tell me a story' },
          { role: 'assistant', content: 'Once upon a time...' },
        ]}
      />
    );

    expect(await screen.findByText('Tell me a story')).toBeInTheDocument();
    expect(await screen.findByText('Once upon a time...')).toBeInTheDocument();
  });

  it('disables the composer when modelChatStatus is not enabled', async () => {
    render(<ModelChat model={modelName} modelChatStatus="pending" />);

    expect(await screen.findByRole('textbox', { name: /Task prompt/i })).toBeDisabled();
    expect(await screen.findByText('Model Deployment in Progress')).toBeInTheDocument();
  });
});
