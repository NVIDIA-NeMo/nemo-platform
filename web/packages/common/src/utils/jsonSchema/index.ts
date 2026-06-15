// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

export { canonicalJson } from './canonical';
export { INFERENCE_MAX_DEPTH, inferJsonSchema } from './inference';
export type { InferOptions, JsonSchema } from './inference';
export { parseAndValidate, validateJsonSchemaDocument } from './validate';
export type { ParseAndValidateResult, ValidationResult } from './validate';
export { buildDatasetMetadata } from './dedupe';
export type { PerFileInferred } from './dedupe';
export { isSchemaAssignableFile } from './schemaAssignable';
