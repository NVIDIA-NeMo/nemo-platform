// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { InferenceParams } from '@nemo/sdk/generated/platform/schema';
import type { BadgeProps } from '@nvidia/foundations-react-core';
import type { AddColumnSelection } from '@studio/components/AddColumnPalette/types';
import type { LucideIcon } from 'lucide-react';

export type StartOptionId = 'ai' | 'template' | 'clone' | 'scratch';

export interface StartOptionTag {
  label: string;
  color: NonNullable<BadgeProps['color']>;
  kind: NonNullable<BadgeProps['kind']>;
}

export interface StartOption {
  id: StartOptionId;
  title: string;
  description: string;
  icon: LucideIcon;
  tag?: StartOptionTag;
  /**
   * Whether this option is wired up. Disabled options still render (so the full set
   * of future entry points is visible) but are no-ops — they cannot be selected and
   * never reveal a detail panel or the Continue footer.
   */
  enabled: boolean;
}

export interface TemplateColumnSpec extends AddColumnSelection {
  /** The column name (Jinja2 identifier); referenced by later columns via `{{ name }}`. */
  name: string;
  /** Field values keyed by `ColumnField.key`. Omit for columns with no seeded fields. */
  values?: Record<string, string>;
}

/** Picking one preloads the build canvas with its columns and any models they reference. */

export interface TemplateModelSpec {
  /** Alias the template's columns reference via `model_alias`. */
  alias: string;
  /** Preferred model URN (e.g. `nvidia/llama-3.3-nemotron-super-49b-v1.5`); optional. */
  model?: string;
  /** Optional inference parameter defaults. */
  inferenceParams?: Partial<InferenceParams>;
}

/**
 * A ready-made recipe shown as a card in the secondary area when the "Start from a
 * template" option is selected. Picking one preloads the build canvas with its columns
 * and any models they reference.
 */
export interface FilesetTemplate {
  /** Stable id passed to {@link CreateFilesetStartProps.onContinue} when chosen. */
  id: string;
  title: string;
  description: string;
  icon: LucideIcon;
  tag: StartOptionTag;
  columns: TemplateColumnSpec[];
  /** Models preloaded into the job config, referenced by the columns' `model_alias`. */
  models?: TemplateModelSpec[];
}

export interface TemplateCardProps {
  template: FilesetTemplate;
  selected: boolean;
  onSelect: () => void;
}

export interface StartOptionCardProps {
  option: StartOption;
  selected: boolean;
  /** Fired on click / keyboard activation. Only invoked for enabled options. */
  onSelect: () => void;
}

export interface DetailPoint {
  icon: LucideIcon;
  title: string;
  description: string;
}

export interface StartOptionDetailProps {
  option: StartOption;
  /** Id of the currently-chosen template, when {@link option} is "template". */
  selectedTemplateId: string | null;
  onSelectTemplate: (templateId: string) => void;
}

export interface CreateFilesetStartProps {
  /**
   * Fired when the user confirms a selected start option via the Continue footer. For
   * the "template" option, the chosen template id is passed as the second argument.
   */
  onContinue: (optionId: StartOptionId, templateId?: string) => void;
}
