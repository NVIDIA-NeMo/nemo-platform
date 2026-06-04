// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ToastProvider } from '@nemo/common/src/providers/toast/ToastProvider';
import type { ModelEntity } from '@nemo/sdk/generated/platform/schema';
import { TooltipProvider } from '@nvidia/foundations-react-core';
import type { Meta, StoryObj } from '@storybook/react';
import { ModelPanel } from '@studio/components/sidePanels/ModelPanels/ModelPanel';

const meta: Meta<typeof ModelPanel> = {
  component: ModelPanel,
  title: 'Side Panels/ModelPanel',
  decorators: [
    (Story) => (
      <TooltipProvider>
        <ToastProvider>
          <div className="p-4 max-w-md border border-base rounded">
            <Story />
          </div>
        </ToastProvider>
      </TooltipProvider>
    ),
  ],
};

export default meta;

type Story = StoryObj<typeof ModelPanel>;

const mockModelEntity: ModelEntity = {
  id: 'model-test-id',
  name: 'meta/llama-3.2-1b-instruct',
  workspace: 'my-workspace',
  created_at: '2025-01-15T10:30:00Z',
  updated_at: '2025-01-15T10:30:00Z',
  description:
    'Llama-3.2-1b is a lightweight language model designed for efficient deployment while maintaining strong capabilities.',
  spec: {
    checkpoint_model_name: 'nvidia/nemo/llama-3_2-1b-instruct-nemo:1.0',
    family: 'llama',
    context_size: 8192,
    base_num_parameters: 1_000_000_000,
    is_chat: true,
    minimum_gpus_all_weights: 1,
    minimum_gpus_lora: 1,
    num_layers: 24,
    hidden_size: 2048,
    num_attention_heads: 32,
    num_kv_heads: 8,
    ffn_hidden_size: 8192,
    vocab_size: 128256,
    tied_embeddings: false,
    gated_mlp: true,
    precision: 'bfloat16',
  },
};

export const Default: Story = {
  args: {
    model: mockModelEntity,
    overviewProps: {
      badges: ['tool-calling', 'reasoning'],
    },
    attributes: {
      SidePanel: {
        open: true,
      },
    },
  },
};

export const MissingModelSpec: Story = {
  args: {
    model: undefined,
  },
};

export const WithAllDetails: Story = {
  args: {
    model: {
      ...mockModelEntity,
      base_model: 'meta/llama-3.2-1b-instruct',
      created_at: '2025-01-15T10:30:00Z',
      fileset: 'my-workspace/my-model-fileset',
      finetuning_type: 'lora',
      api_endpoint: {
        format: 'openai',
        url: 'https://api.example.com/v1/models/llama-3.2-1b-instruct',
        model_id: 'llama-3.2-1b-instruct',
        api_key: 'sk-1234567890abcdef',
      },
      prompt: {
        system_prompt: `You are a helpful assistant. You are designed to answer questions, provide recommendations, and help users accomplish their goals efficiently and accurately. Make sure your responses are always polite, concise, and informative. If you are ever unsure of the correct answer, feel free to let the user know or suggest a way to find the required information. Remember to maintain a positive and supportive tone in all circumstances, regardless of question complexity or content. Your goals include being accessible, helpful, and trustworthy, and you should always strive to present information in a clear, easy-to-understand manner. Please ensure you respect user privacy and never ask for private information unless it is absolutely necessary for the task. If clarification is needed, ask thoughtful follow-up questions.`,
        icl_few_shot_examples:
          'User: What is the capital of France?\nAssistant: The capital of France is Paris.\n\nUser: Explain quantum computing.\nAssistant: Quantum computing uses quantum mechanics to process information in ways that differ from classical computers.',
      },
      adapters: [
        {
          name: 'customer-support-adapter',
          fileset: 'my-workspace/customer-support-lora',
          finetuning_type: 'lora_merged',
          description: 'LoRA adapter for customer support tone',
          workspace: 'my-workspace',
        },
      ],
    },
    overviewProps: {
      status: 'READY',
      badges: ['tool-calling', 'reasoning'],
    },
    deployment: {
      id: '123',
      created_at: '2025-01-01T00:00:00Z',
      updated_at: '2025-01-01T00:00:00Z',
      name: 'meta/llama-3.2-1b-instruct',
      workspace: 'my-workspace',
      status: 'READY',
      entity_version: 1,
      config: 'default',
      config_version: 1,
    },
    artifactData: {
      backend_engine: 'nemo',
      gpu_architecture: 'Ampere',
      tensor_parallelism: 2,
    },
    customizationJobId: 'cust-job-abc-123',
    attributes: {
      SidePanel: {
        open: true,
      },
    },
  },
};
