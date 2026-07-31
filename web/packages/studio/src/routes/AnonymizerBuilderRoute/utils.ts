// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { DataDesignerModelOption } from '@studio/components/NewDataDesignerJobForm/utils';
import {
  STRATEGY_REWRITE,
  TAB_MODEL_SETTINGS,
  TAB_SOURCE,
  type BuilderTab,
  type Strategy,
} from '@studio/routes/AnonymizerBuilderRoute/constants';

export const OUTPUT_HEADING_REPLACED = 'Replaced';
export const OUTPUT_HEADING_REWRITTEN = 'Rewritten';

export const isGlinerModel = (model: DataDesignerModelOption): boolean =>
  /gliner/i.test(model.name) || /gliner/i.test(model.served_model_name ?? '');

/** Only `roleModels` lives on Model Settings; an empty list must not read as "models only". */
export const tabForValidationErrors = (fields: readonly string[]): BuilderTab =>
  fields.length > 0 && fields.every((field) => field === 'roleModels')
    ? TAB_MODEL_SETTINGS
    : TAB_SOURCE;

/** The output column only exists once results land, so the skeleton reads the strategy instead. */
export const outputHeadingForStrategy = (strategy: Strategy): string =>
  strategy === STRATEGY_REWRITE ? OUTPUT_HEADING_REWRITTEN : OUTPUT_HEADING_REPLACED;
