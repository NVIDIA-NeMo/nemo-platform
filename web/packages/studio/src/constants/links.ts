// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

const BASE_DOCS_URL = 'https://nvidia-nemo.github.io/';
const PLATFORM_DOCS_REPO_NAME = 'nemo-platform';
const DOCS_BASE_URL = `${BASE_DOCS_URL}${PLATFORM_DOCS_REPO_NAME}/main/`;

// Studio documentation links
export const LINK_DOCS_STUDIO = `${DOCS_BASE_URL}studio/`;
export const LINK_DOCS_STUDIO_CUSTOMIZATION =
  'https://docs.nvidia.com/nemo/microservices/latest/customizer/index.html';
export const LINK_DOCS_STUDIO_EVALUATION = `${DOCS_BASE_URL}evaluator/`;
export const LINK_DOCS_PROJECT = `${DOCS_BASE_URL}studio/projects/`;
export const LINK_DOCS_DATASETS = `${DOCS_BASE_URL}get-started/concepts/projects/`;
export const LINK_DOCS_MODELS = `${DOCS_BASE_URL}run-inference/about/`;
export const LINK_DOCS_DEPLOYMENTS =
  'https://docs.nvidia.com/nemo/microservices/latest/run-inference/tutorials/deploy-models.html';

/** Inference providers, gateway routing, and external endpoints */
export const LINK_DOCS_INFERENCE_PROVIDERS = `${DOCS_BASE_URL}run-inference/about/`;
export const LINK_DOCS_SAFE_SYNTHESIZER =
  'https://docs.nvidia.com/nemo/microservices/latest/safe-synthesizer/about/index.html';

// SDK documentation links
export const LINK_DOCS_SDK = DOCS_BASE_URL;

// Fine Tune documentation links
export const LINK_DOCS_FINE_TUNE_CONFIGURATION_DECISIONS =
  'https://docs.nvidia.com/nemo/microservices/latest/fine-tune/tutorials/understand-configurations-and-models.html#making-configuration-decisions';
export const LINK_DOCS_FINE_TUNE_DATASET_FORMAT_REQUIREMENTS =
  'https://docs.nvidia.com/nemo/microservices/latest/fine-tune/models/data-format.html';
export const LINK_DOCS_FINE_TUNE_HYPERPARAMETERS =
  'https://docs.nvidia.com/nemo/microservices/latest/customizer/about.html#hyperparameters';
export const LINK_DOCS_FINE_TUNE_MODEL_ENTITIES =
  'https://docs.nvidia.com/nemo/microservices/latest/customizer/manage-model-entities/index.html#manage-model-entities-for-customization';

// Guardrail documentation links
export const LINK_DOCS_GUARDRAIL = `${DOCS_BASE_URL}guardrails/`;

// Top-level NeMo "Concepts" documentation links
export const LINK_DOCS_CONCEPTS_CUSTOMIZATION =
  'https://docs.nvidia.com/nemo/microservices/latest/about/core-concepts/customization.html';

export const LINK_DOCS_SEQUENCE_PACKING =
  'https://docs.nvidia.com/nemo/microservices/latest/about/core-concepts/customization.html#sequence-packing';

// Third party documentation links
export const LINK_DOCS_OPENAI_FUNCTION_SCHEMA =
  'https://platform.openai.com/docs/guides/function-calling#defining-functions';

// Support links
export const LINK_GITHUB_ISSUES = `https://github.com/NVIDIA-NeMo/${PLATFORM_DOCS_REPO_NAME}/issues`;

// Evaluation documentation links
export const LINK_EVAL_DOCS_METRICS = `${DOCS_BASE_URL}evaluator/metrics/`;
export const LINK_EVAL_DOCS_BENCHMARKS =
  'https://docs.nvidia.com/nemo/microservices/latest/evaluator/benchmarks/index.html';
export const LINK_EVAL_DOCS_BENCHMARKS_INDUSTRY =
  'https://docs.nvidia.com/nemo/microservices/latest/evaluator/benchmarks/industry.html';

// Jobs documentation links
export const LINK_DOCS_JOBS = `${DOCS_BASE_URL}studio/?#jobs`;

// Secrets documentation links
export const LINK_DOCS_SECRETS = `${DOCS_BASE_URL}get-started/concepts/manage-secrets/`;

// Experiments
export const LINK_DOCS_EXPERIMENTS_CLI = `${DOCS_BASE_URL}experiments/cli/`;
