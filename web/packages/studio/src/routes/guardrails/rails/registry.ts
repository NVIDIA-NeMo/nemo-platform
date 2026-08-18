// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { selfCheckRail } from '@studio/routes/guardrails/rails/selfCheck';
import type { RailDefinition } from '@studio/routes/guardrails/rails/types';

/**
 * The rails Studio can configure, in list order. Adding one means adding a definition
 * here — see `selfCheck/` for the shape. Rails without a definition are left untouched in
 * the saved config.
 */
export const RAIL_DEFINITIONS: RailDefinition[] = [selfCheckRail];
