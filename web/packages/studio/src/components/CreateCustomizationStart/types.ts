// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { BadgeProps } from '@nvidia/foundations-react-core';
import type { StartOption as SharedStartOption } from '@studio/components/StartOptions/types';
import type { CustomizationFormFields } from '@studio/util/forms/customization';

export type StartOptionId = 'json' | 'template' | 'scratch';

export type StartOption = SharedStartOption<StartOptionId>;

/**
 * A curated recipe provisions first and is keyed by a code-defined `id`; a saved template
 * provisions nothing and is keyed by its entity `name`. The union keeps the two distinct.
 */
export type TemplateSelection = { kind: 'curated'; id: string } | { kind: 'saved'; name: string };

export interface TemplateBadge {
  label: string;
  color: NonNullable<BadgeProps['color']>;
}

/**
 * A curated recipe and a saved template flattened to the one shape the card renders, so
 * both kinds sit in a single list and stay visually comparable. Where they genuinely
 * differ — provisioning stats, the delete control — the field is simply absent.
 */
export interface TemplateCardModel {
  key: string;
  selection: TemplateSelection;
  /** "NVIDIA" for shipped recipes, "User created" for the user's own. */
  publisher: string;
  title: string;
  description?: string;
  badges: TemplateBadge[];
  /** Muted footer lines: provisioning stats for a recipe, model + dataset for a saved one. */
  footer?: string[];
  requiresHfToken?: boolean;
  /** False when a saved payload can no longer be turned back into form fields. */
  applicable: boolean;
  /** Saved only. */
  onDelete?: () => void;
  isDeleting?: boolean;
}

export interface TemplateCardProps {
  model: TemplateCardModel;
  selected: boolean;
  onSelect: () => void;
}

export interface TemplateGridProps {
  workspace: string;
  selectedTemplate: TemplateSelection | null;
  onSelectTemplate: (selection: TemplateSelection | null) => void;
}

export interface JsonConfigPanelProps {
  /**
   * Fired after every edit: the form values when the config is loadable, null when it
   * isn't — so clearing a good config back to a broken one also disables Continue.
   */
  onValidConfig: (fields: CustomizationFormFields | null) => void;
}

export interface StartOptionDetailProps {
  option: StartOption;
  workspace: string;
  /** The currently-picked template, when {@link option} is "template". */
  selectedTemplate: TemplateSelection | null;
  onSelectTemplate: (selection: TemplateSelection | null) => void;
  onValidConfig: (fields: CustomizationFormFields | null) => void;
}

/**
 * What the user confirmed via the Continue footer. Every arm but "scratch" resolves to
 * concrete form values, so the route never has to know how they were produced.
 */
export type StartSelection =
  | { optionId: 'scratch' }
  | { optionId: 'json'; initialValues: CustomizationFormFields }
  | { optionId: 'template'; initialValues: CustomizationFormFields };

export interface CreateCustomizationStartProps {
  /** Workspace the template option registers its models and datasets into. */
  workspace: string;
  /** Fired when the user confirms a selected start option via the Continue footer. */
  onContinue: (selection: StartSelection) => void;
}
