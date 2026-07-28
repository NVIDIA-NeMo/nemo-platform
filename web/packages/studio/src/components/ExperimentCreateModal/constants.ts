/*
 * SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 *
 * NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
 * property and proprietary rights in and to this material, related
 * documentation and any modifications thereto. Any use, reproduction,
 * disclosure or distribution of this material and related documentation
 * without an express license agreement from NVIDIA CORPORATION or
 * its affiliates is strictly prohibited.
 */

import { CreateExperimentBody } from '@nemo/sdk/generated/platform/zod/experiments/createExperiment';
import { workspaceInputSchema } from '@studio/constants/zod';

// Override the SDK-generated `name` validation — the generated zod uses the DTO's loose
// string pattern; we validate against the stricter workspace-name rules so the user sees
// a useful inline error instead of a 422 toast.
export const experimentCreateSchema = CreateExperimentBody.extend({
  name: workspaceInputSchema,
});

export type ExperimentCreateFormFields = typeof experimentCreateSchema._type;
