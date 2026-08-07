// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ToastProvider } from '@nemo/common/src/providers/toast/ToastProvider';
import type { Meta, StoryObj } from '@storybook/react';
import { http, HttpResponse } from 'msw';
import { CustomizationDetailsPanel } from '@studio/components/CustomizationDetailsPanel';

const WORKSPACE = 'default';
const JOB_NAME = 'mock-grpo-preview';

const MOCK_GRPO_JOB = {
  id: 'grpo-mock-001',
  name: JOB_NAME,
  description: 'GRPO preference optimization — UI preview',
  workspace: WORKSPACE,
  created_at: new Date(Date.now() - 90 * 60 * 1000).toISOString(),
  updated_at: new Date(Date.now() - 2 * 60 * 1000).toISOString(),
  status: 'running',
  ownership: { created_by: 'htolentino@nvidia.com' },
  spec: {
    model: 'meta/llama-3.1-8b-instruct',
    dataset: `${WORKSPACE}/grpo-prompts-v1`,
    training: {
      type: 'grpo',
      epochs: 3,
      learning_rate: 1e-5,
      batch_size: 32,
      micro_batch_size: 2,
      max_seq_length: 2048,
      warmup_steps: 100,
      num_generations: 8,
      epsilon: 0.2,
      kl_coeff: 0.05,
      reward_model: `${WORKSPACE}/reward-model-v1`,
      parallelism: {
        num_nodes: 2,
        num_gpus_per_node: 8,
        tensor_parallel_size: 2,
        pipeline_parallel_size: 1,
        context_parallel_size: 1,
        sequence_parallel: false,
      },
    },
    output: { name: 'llama-3.1-8b-grpo-v1' },
  },
  status_details: {
    phase: 'training',
    step: 450,
    max_steps: 1200,
    num_epochs: 3,
    epoch: 1,
    percentage_done: 37.5,
    mean_reward: 0.66,
    reward_std: 0.11,
    clip_fraction: 0.15,
    kl_divergence: 0.032,
    lr: 8.2e-6,
    grad_norm: 0.812,
    checkpoint_path: '/checkpoints/llama-3.1-8b-grpo-v1/step-450',
    metrics: {
      mean_reward: [
        { step: 50, epoch: 1, value: 0.38 },
        { step: 100, epoch: 1, value: 0.42 },
        { step: 150, epoch: 1, value: 0.47 },
        { step: 200, epoch: 1, value: 0.51 },
        { step: 250, epoch: 1, value: 0.55 },
        { step: 300, epoch: 1, value: 0.58 },
        { step: 350, epoch: 1, value: 0.61 },
        { step: 400, epoch: 1, value: 0.63 },
        { step: 450, epoch: 1, value: 0.66 },
      ],
      reward_std: [
        { step: 50, epoch: 1, value: 0.21 },
        { step: 100, epoch: 1, value: 0.18 },
        { step: 150, epoch: 1, value: 0.16 },
        { step: 200, epoch: 1, value: 0.15 },
        { step: 250, epoch: 1, value: 0.14 },
        { step: 300, epoch: 1, value: 0.13 },
        { step: 350, epoch: 1, value: 0.12 },
        { step: 400, epoch: 1, value: 0.12 },
        { step: 450, epoch: 1, value: 0.11 },
      ],
      clip_fraction: [
        { step: 100, epoch: 1, value: 0.28 },
        { step: 200, epoch: 1, value: 0.22 },
        { step: 300, epoch: 1, value: 0.19 },
        { step: 400, epoch: 1, value: 0.16 },
        { step: 450, epoch: 1, value: 0.15 },
      ],
    },
  },
};

const MOCK_LOGS = [
  { timestamp: new Date(Date.now() - 88 * 60 * 1000).toISOString(), message: '[INFO] GRPO job started', level: 'INFO' },
  { timestamp: new Date(Date.now() - 85 * 60 * 1000).toISOString(), message: '[INFO] Loading model meta/llama-3.1-8b-instruct', level: 'INFO' },
  { timestamp: new Date(Date.now() - 80 * 60 * 1000).toISOString(), message: '[INFO] Dataset default/grpo-prompts-v1 loaded: 12,480 prompts', level: 'INFO' },
  { timestamp: new Date(Date.now() - 75 * 60 * 1000).toISOString(), message: '[INFO] Reward model default/reward-model-v1 connected', level: 'INFO' },
  { timestamp: new Date(Date.now() - 60 * 60 * 1000).toISOString(), message: '[INFO] Epoch 1 started', level: 'INFO' },
  { timestamp: new Date(Date.now() - 30 * 60 * 1000).toISOString(), message: '[INFO] step=300 mean_reward=0.58 clip_fraction=0.19 kl=0.029', level: 'INFO' },
  { timestamp: new Date(Date.now() - 15 * 60 * 1000).toISOString(), message: '[INFO] step=400 mean_reward=0.63 clip_fraction=0.16 kl=0.031', level: 'INFO' },
  { timestamp: new Date(Date.now() - 5 * 60 * 1000).toISOString(), message: '[INFO] step=450 mean_reward=0.66 clip_fraction=0.15 kl=0.032', level: 'INFO' },
];

const handlers = [
  http.get(
    `/apis/jobs/v2/workspaces/${WORKSPACE}/jobs/${JOB_NAME}`,
    () => HttpResponse.json(MOCK_GRPO_JOB)
  ),
  http.get(
    `/apis/jobs/v2/workspaces/${WORKSPACE}/jobs/${JOB_NAME}/logs`,
    () => HttpResponse.json({ data: MOCK_LOGS })
  ),
  http.get(
    `/apis/platform/v1/workspaces/${WORKSPACE}/filesets/:name`,
    () => HttpResponse.json({ data: [] })
  ),
  http.get(
    `/apis/files/v1/workspaces/${WORKSPACE}/filesets/:name`,
    () => HttpResponse.json({ files: [] })
  ),
];

const meta = {
  component: CustomizationDetailsPanel,
  title: 'Components/CustomizationDetailsPanel',
  decorators: [
    (Story) => (
      <ToastProvider>
        <Story />
      </ToastProvider>
    ),
  ],
  parameters: {
    layout: 'padded',
    router: { initialPath: `/workspaces/${WORKSPACE}/customizations/${JOB_NAME}` },
    msw: { handlers },
  },
} satisfies Meta<typeof CustomizationDetailsPanel>;

export default meta;
type Story = StoryObj<typeof meta>;

export const GrpoJobRunning: Story = {
  name: 'GRPO Job — Running',
  args: {
    customizationJobName: JOB_NAME,
    workspace: WORKSPACE,
  },
};
