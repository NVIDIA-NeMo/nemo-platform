// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * Inference parameter type + defaults — shared between the ParamsPopover
 * component and the route state that owns the panel params.
 *
 * Lives in its own module (not co-located with the ParamsPopover component)
 * so the component file can stay a pure component export and not trip
 * `react-refresh/only-export-components`.
 */

export interface InferenceParams {
  temperature: number;
  top_p: number;
  top_k: number;
  max_tokens: number;
}

export const DEFAULT_INFERENCE_PARAMS: InferenceParams = {
  temperature: 0.7,
  top_p: 0.95,
  top_k: 40,
  max_tokens: 512,
};
