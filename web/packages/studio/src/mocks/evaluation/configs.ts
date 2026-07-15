// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

export const mockEvalConfigBigCode = {
  id: 'eval-config-DptKNnopfGLCSGuKHksGPp',
  namespace: '-',
  name: 'bigcode evaluation harness cfg',
  custom_fields: { 'bigcode_evaluation_harness-evaluation-config': '' },
  type: 'bigcode_evaluation_harness',
  tasks: {
    default: {
      type: 'humaneval',
      dataset: {
        files_url: 'input.json',
      },
      params: {
        batch_size: 1,
        max_length_generation: 512,
        temperature: 1.0,
        top_k: 1,
        top_p: 0.0,
        n_samples: 1,
        num_chunks: 1,
      },
      metrics: { bleu: { type: 'bleu' } },
    },
  },
  params: {},
};

export const mockEvalConfigLmHarness = {
  id: 'eval-config-Sp6oJ264eR7MQTepRoaPAh',
  namespace: '-',
  name: 'eval-config-Sp6oJ264eR7MQTepRoaPAh',
  custom_fields: { 'lm_eval_harness-evaluation-config': '' },
  type: 'lm_eval_harness',
  params: {
    use_greedy: true,
    temperature: 1.0,
    top_k: 1,
    top_p: 0.0,
    stop: ['<|endoftext|>', '<extra_id_1>'],
    tokens_to_generate: 1024,
  },
  tasks: {
    default: {
      type: 'humaneval',
      dataset: {
        files_url: 'input.json',
      },
      params: {
        batch_size: 1,
        max_length_generation: 512,
        temperature: 1.0,
        top_k: 1,
        top_p: 0.0,
        n_samples: 1,
        num_chunks: 1,
      },
      metrics: { bleu: { type: 'bleu' } },
    },
  },
};

export const mockEvalConfigCustom = {
  id: 'eval-config-K8Kb4x7McMQqco1SAAk5VG',
  namespace: '-',
  name: 'eval-config-K8Kb4x7McMQqco1SAAk5VG',
  custom_fields: { 'custom-evaluation-config': '' },
  type: 'custom',
  schema_version: '1.0',
  type_prefix: null,
  version_id: '',

  tasks: {
    default: {
      type: 'humaneval',
      params: {
        tokens_to_generate: 200,
        temperature: 0.7,
        top_k: 20,
        n_samples: -1,
      },
      dataset: {
        files_url: 'nds:evaldata_test_ypolius_1/input.json',
      },
      metrics: {
        accuracy: { type: 'accuracy' },
        bleu: { type: 'bleu' },
        rouge: { type: 'rouge' },
        em: { type: 'em' },
        f1: { type: 'f1' },
      },
    },
  },
};

// Mock custom config with multiple tasks
export const mockEvalConfigCustomMultiTask = {
  id: 'eval-config-MultiTask123',
  namespace: '-',
  name: 'multi-task-eval-config',
  custom_fields: { 'multi-task-evaluation-config': '' },
  type: 'custom',
  schema_version: '1.0',
  type_prefix: null,
  version_id: '',

  tasks: {
    'llm-task': {
      type: 'chat-completion',
      params: {
        max_tokens: 150,
        temperature: 0.8,
        top_p: 0.95,
      },
      dataset: {
        files_url: 'hf://datasets/test-user/llm-dataset/data.jsonl',
      },
      metrics: {
        'llm-judge': {
          type: 'llm-judge',
          params: {
            prompt: 'Evaluate the response quality',
            model: 'gpt-4',
          },
        },
        bleu: { type: 'bleu' },
      },
    },
    'data-quality-task': {
      type: 'data',
      params: {},
      dataset: {
        files_url: 'nds:default/evaldata_quality_check/validation.json',
      },
      metrics: {
        accuracy: { type: 'accuracy' },
        f1: { type: 'f1' },
        em: { type: 'em' },
      },
    },
    'similarity-task': {
      type: 'default',
      params: {
        threshold: 0.85,
      },
      dataset: {
        files_url: 'nds:default/evaldata_similarity/test.json',
      },
      metrics: {
        rouge: { type: 'rouge' },
        bleu: { type: 'bleu' },
      },
    },
  },
};

// Mock custom config with user-named metrics (keys don't match types)
export const mockEvalConfigCustomUserNamedMetrics = {
  id: 'eval-config-UserNamed123',
  namespace: '-',
  name: 'user-named-metrics-config',
  custom_fields: { 'custom-evaluation-config': '' },
  type: 'custom',
  schema_version: '1.0',
  type_prefix: null,
  version_id: '',

  tasks: {
    'my-task': {
      type: 'chat-completion',
      params: {
        max_tokens: 200,
        temperature: 0.7,
      },
      dataset: {
        files_url: 'hf://datasets/user/test-dataset/data.jsonl',
      },
      metrics: {
        'my-custom-bleu-score': {
          type: 'bleu',
          params: {
            references: ['{{sample.reference}}'],
            candidate: '{{sample.output}}',
          },
        },
        'accuracy-check-v2': {
          type: 'em',
          params: {
            ground_truth: '{{sample.expected}}',
            prediction: '{{sample.output}}',
          },
        },
        'quality-judge': {
          type: 'llm-judge',
          params: {
            prompt: 'Rate the quality',
            model: 'gpt-4',
          },
        },
      },
    },
  },
};

export const mockEvalConfigLLMAsJudge = {
  id: 'eval-config-U1jRPhTCG8NFPAf27Lucfb',
  namespace: '-',
  name: 'eval-config-U1jRPhTCG8NFPAf27Lucfb',
  custom_fields: { 'llm_as_a_judge-evaluation-config': '' },
  type: 'llm_as_a_judge',
  schema_version: '1.0',
  type_prefix: null,
  version_id: '',
  tasks: {
    default: {
      type: 'custom',
      dataset: {
        files_url: 'nds:hhud-mtbench-custom-dataset-questions',
      },
      params: {
        judge_model: {
          schema_version: '1.0',
          description: undefined,
          type_prefix: null,
          namespace: null,
          project: null,
          version_id: '',
          api_endpoint: {
            url: 'https://integrate.api.nvidia.com/v1/completions',
            model_id: 'meta/llama-3.1-70b-instruct',
            format: 'nim',
          },
        },
        judge_inference_params: {
          temperature: 0.7,
          top_k: 40,
          top_p: 0.1,
          stop: [],
          tokens_to_generate: 1024,
        },
        temperature: 0.75,
        top_k: 0,
        top_p: 0.75,
        stop: [],
        tokens_to_generate: 1024,
      },
    },
  },
};

export const mockEvalConfigRetriever = {
  id: 'eval-config-VZxkkG7cuqx4kx4evwLFX5',
  namespace: '-',
  name: 'eval-config-VZxkkG7cuqx4kx4evwLFX5',
  custom_fields: { 'retriever-evaluation-config': '' },
  type: 'retriever',
  schema_version: '1.0',
  type_prefix: null,
  version_id: '',
  tasks: {
    default: {
      type: 'beir',
      dataset: {
        files_url: 'fiqa',
        format: 'beir',
      },
      metrics: {
        recall_5: { type: 'recall_5' },
        ndcg_cut_5: { type: 'ndcg_cut_5' },
        recall_10: { type: 'recall_10' },
        ndcg_cut_10: { type: 'ndcg_cut_10' },
      },
    },
  },
};

export const mockEvalConfigRag = {
  id: 'eval-config-65jFjPQMBBFmLQobZ3fX6T',
  namespace: '-',
  name: 'eval-config-65jFjPQMBBFmLQobZ3fX6T',
  custom_fields: { 'rag-evaluation-config': '' },
  schema_version: '1.0',
  type_prefix: null,
  version_id: '',
  type: 'rag',
  tasks: {
    default: {
      type: 'beir',
      dataset: {
        files_url: 'fiqa',
        format: 'beir',
      },
      metrics: {
        recall_5: { type: 'recall_5' },
        ndcg_cut_5: { type: 'ndcg_cut_5' },
        recall_10: { type: 'recall_10' },
        ndcg_cut_10: { type: 'ndcg_cut_10' },
        faithfulness: { type: 'faithfulness' },
      },
      params: {
        judge_llm: {
          schema_version: '1.0',
          description: undefined,
          type_prefix: null,
          namespace: null,
          project: null,
          version_id: '',
          api_endpoint: {
            url: 'http://nemo-deployment-management.nemo-deployment-management.svc.cluster.local:8001/v1/chat/completions',
            model_id: 'meta/llama-3.1-70b-instruct',
            format: 'nim',
          },
        },
        judge_embeddings: {
          schema_version: '1.0',
          description: undefined,
          type_prefix: null,
          namespace: null,
          project: null,
          version_id: '',
          api_endpoint: {
            url: 'http://nemo-embedding-ms.nemo-retrieval.svc.cluster.local:8080/v1/embeddings',
            model_id: 'nvidia-nv-embedqa-e5-v5',
            format: 'nim',
          },
        },
        judge_timeout: 300,
        judge_max_retries: 5,
        judge_max_workers: 16,
      },
    },
  },
};

export const mockEvalConfigs = [
  mockEvalConfigBigCode,
  mockEvalConfigLmHarness,
  mockEvalConfigCustom,
  mockEvalConfigLLMAsJudge,
  mockEvalConfigRetriever,
  mockEvalConfigRag,
];
