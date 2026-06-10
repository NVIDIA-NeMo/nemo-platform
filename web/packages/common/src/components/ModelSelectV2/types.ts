// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ModelWorkspaceGroup } from '@nemo/common/src/api/models/useModels';
import type { InferenceParams } from '@nemo/sdk/generated/platform/schema';

export interface ModelSelection {
  /** Model URN (e.g. "workspace/model_name") */
  model: string;
  /** Adapter name, if an adapter was selected instead of the base model */
  adapter?: string;
}

export interface ModelSelectV2Props {
  /** Currently selected model (and optional adapter) */
  value: ModelSelection | null;
  /** Called when user selects a model or adapter */
  onValueChange: (selection: ModelSelection) => void;
  /** Models grouped by workspace */
  groups: ModelWorkspaceGroup[];
  /** Whether models are still loading */
  loading?: boolean;
  /** Whether the component is disabled */
  disabled?: boolean;
  /** Placeholder text for the model trigger button */
  placeholder?: string;
  /** Show the Custom/Base segmented control toggle */
  showModelTypeToggle?: boolean;
  /** Default active segment when toggle is shown */
  defaultModelType?: 'custom' | 'base';
  /** Show the params button alongside the model button */
  showParams?: boolean;
  /**
   * Hide each model's adapter sub-list. When true, models render as flat,
   * directly-selectable items even if they have adapters.
   *
   * Use this when only base models are valid selections (e.g. fine-tuning
   * source models, where the customizer requires a model URN with a
   * fileset, not an adapter).
   */
  hideAdapters?: boolean;
  /** Make the component fill the width of its container */
  fullWidth?: boolean;
  /** Preferred side for the dropdown content */
  dropdownSide?: 'top' | 'bottom';
  /** Current inference parameter values */
  inferenceParams?: Partial<InferenceParams>;
  /** Called when the user changes any inference parameter */
  onInferenceParamsChange?: (params: Partial<InferenceParams>) => void;
  /** Called when the model dropdown opens or closes */
  onOpenChange?: (open: boolean) => void;
  /** aria-label for the button group */
  'aria-label'?: string;
}

export type ModelType = 'custom' | 'base';
