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

import {
  EXPERIMENT_SETTINGS_DEFAULTS,
  experimentSettingsSchemaShape,
} from '@studio/components/evaluation/shared/experimentSettings';
import { workspaceInputSchema } from '@studio/constants/zod';
import { z } from 'zod';

// The name is validated against the stricter workspace-name rules rather than the DTO's loose
// string pattern, so the user sees a useful inline error instead of a 422 toast. Everything below
// the name is the shared experiment-settings shape, so this form, the edit form, and the
// evaluation form's "new experiment" path cannot drift apart.
export const experimentCreateSchema = z.object({
  name: workspaceInputSchema,
  ...experimentSettingsSchemaShape,
});

export type ExperimentCreateFormFields = z.infer<typeof experimentCreateSchema>;

export const experimentCreateDefaults: ExperimentCreateFormFields = {
  name: '',
  ...EXPERIMENT_SETTINGS_DEFAULTS,
};
