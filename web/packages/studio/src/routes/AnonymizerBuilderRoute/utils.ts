// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { DataDesignerModelOption } from '@studio/components/NewDataDesignerJobForm/utils';
import {
  TAB_MODEL_SETTINGS,
  TAB_SOURCE,
  type BuilderTab,
} from '@studio/routes/AnonymizerBuilderRoute/constants';

export const isGlinerModel = (model: DataDesignerModelOption): boolean =>
  /gliner/i.test(model.name) || /gliner/i.test(model.served_model_name ?? '');

/**
 * Pick the tab that shows the failing fields. Only `roleModels` lives on Model Settings, so
 * anything else — including an empty list, which must never read as "models only" — is Source.
 */
export const tabForValidationErrors = (fields: readonly string[]): BuilderTab =>
  fields.length > 0 && fields.every((field) => field === 'roleModels')
    ? TAB_MODEL_SETTINGS
    : TAB_SOURCE;
