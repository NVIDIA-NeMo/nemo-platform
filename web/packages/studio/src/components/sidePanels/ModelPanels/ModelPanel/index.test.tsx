// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ModelEntity } from '@nemo/sdk/generated/platform/schema';
import { ModelPanel } from '@studio/components/sidePanels/ModelPanels/ModelPanel';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { render, screen } from '@testing-library/react';

const minimalModelEntity: ModelEntity = {
  id: 'model-test-id',
  name: 'test-model',
  workspace: 'my-workspace',
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-01T00:00:00Z',
  api_endpoint: {
    url: 'http://localhost:8000/v1',
    model_id: 'test-model',
  },
  spec: {
    checkpoint_model_name: 'nvidia/test:1.0',
    family: 'llama',
    context_size: 4096,
    base_num_parameters: 500_000_000,
    num_layers: 12,
    hidden_size: 1024,
    num_attention_heads: 16,
    num_kv_heads: 16,
    ffn_hidden_size: 4096,
    vocab_size: 32000,
    tied_embeddings: false,
    gated_mlp: true,
    precision: 'bfloat16',
  },
};

describe('ModelPanel', () => {
  it('renders empty state when no model is provided', () => {
    render(
      <TestProviders>
        <ModelPanel open onOpenChange={() => {}} />
      </TestProviders>
    );

    expect(screen.getByText('Awaiting Model Selection')).toBeInTheDocument();
    expect(screen.getByText('Select a base model to get started')).toBeInTheDocument();
  });

  it('renders model name in heading when model is provided', () => {
    render(
      <TestProviders>
        <ModelPanel model={minimalModelEntity} open onOpenChange={() => {}} />
      </TestProviders>
    );

    expect(screen.getByRole('heading', { name: 'test-model' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Model Details' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Chat Playground' })).toBeInTheDocument();
  });

  it('renders Model Details tab content when model is provided', () => {
    render(
      <TestProviders>
        <ModelPanel model={minimalModelEntity} open onOpenChange={() => {}} />
      </TestProviders>
    );

    expect(screen.getByText('Base Model Parameters')).toBeInTheDocument();
    expect(screen.getByText('4096')).toBeInTheDocument();
    expect(screen.getByText('500 million')).toBeInTheDocument();
  });
});
