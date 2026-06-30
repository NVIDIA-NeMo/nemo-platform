// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { DataFileRow } from '@studio/components/FileRowEditor/types';

/**
 * Sample SFT dataset rows for the Storybook story and unit tests. Not imported by the
 * component itself — `FileRowEditor` defaults to an empty dataset so it ships no demo data.
 *
 * The shape is intentionally varied so the schema-inference paths are exercised: `topic`
 * is high-cardinality (free-text input), `difficulty` is low-cardinality (enum dropdown),
 * `quality` is a float, and `metadata` is a nested object (JSON cell).
 */
export const SAMPLE_ROWS: DataFileRow[] = [
  {
    id: 1043,
    topic: 'CUDA streams',
    difficulty: 'medium',
    instruction: 'How can I overlap host-to-device data transfers with kernel execution?',
    response: 'Use cudaMemcpyAsync on multiple non-default streams with pinned host memory…',
    quality: 4.6,
    metadata: { source: 'developer-docs', tokens: 118, verified: true },
  },
  {
    id: 1044,
    topic: 'Triton Inference Server',
    difficulty: 'hard',
    instruction: 'What is the difference between dynamic batching and sequence batching?',
    response:
      'Dynamic batching groups independent requests; sequence batching keeps stateful requests…',
    quality: 4.8,
    metadata: { source: 'developer-docs', tokens: 156, verified: true },
  },
  {
    id: 1045,
    topic: 'TensorRT',
    difficulty: 'medium',
    instruction: 'How do I convert an ONNX model to a TensorRT engine?',
    response:
      'Use trtexec or the TensorRT API to parse the ONNX graph, then build and serialize an optimized engine for your target GPU. For dynamic input shapes, define an optimization profile before building.',
    quality: 4.5,
    metadata: { source: 'developer-docs', tokens: 142, verified: true },
  },
  {
    id: 1046,
    topic: 'NCCL',
    difficulty: 'hard',
    instruction: 'Why does all-reduce hang across multiple nodes?',
    response:
      'Check that NCCL_SOCKET_IFNAME matches your network interface and the ports are open…',
    quality: 4.2,
    metadata: { source: 'developer-docs', tokens: 97, verified: false },
  },
  {
    id: 1047,
    topic: 'cuDNN',
    difficulty: 'easy',
    instruction: 'What is cuDNN used for?',
    response: 'cuDNN is a GPU-accelerated library of primitives for deep neural networks…',
    quality: 4.9,
    metadata: { source: 'developer-docs', tokens: 73, verified: true },
  },
  {
    id: 1048,
    topic: 'RAPIDS',
    difficulty: 'medium',
    instruction: 'How do I move a pandas DataFrame to the GPU?',
    response: 'Use cudf.from_pandas to create a GPU DataFrame backed by the same columns…',
    quality: 4.4,
    metadata: { source: 'developer-docs', tokens: 88, verified: true },
  },
  {
    id: 1049,
    topic: 'Nsight Systems',
    difficulty: 'easy',
    instruction: 'What does Nsight Systems profile?',
    response: 'It captures a system-wide timeline of CPU and GPU activity, CUDA calls and memory…',
    quality: 4.7,
    metadata: { source: 'developer-docs', tokens: 101, verified: true },
  },
  {
    id: 1050,
    topic: 'MIG',
    difficulty: 'hard',
    instruction: 'How do I partition an A100 with MIG?',
    response: 'Enable MIG mode with nvidia-smi then create GPU and compute instances…',
    quality: 4.3,
    metadata: { source: 'developer-docs', tokens: 110, verified: false },
  },
  {
    id: 1051,
    topic: 'DALI',
    difficulty: 'medium',
    instruction: 'Can DALI run augmentation on the GPU?',
    response: 'Yes, the DALI pipeline executes data loading and augmentation on the GPU…',
    quality: 4.5,
    metadata: { source: 'developer-docs', tokens: 84, verified: true },
  },
  {
    id: 1052,
    topic: 'cuBLAS',
    difficulty: 'easy',
    instruction: 'What precision modes does cuBLAS support?',
    response: 'cuBLAS supports FP32, FP16, BF16, and TF32 tensor-core math modes…',
    quality: 4.6,
    metadata: { source: 'developer-docs', tokens: 79, verified: true },
  },
];
