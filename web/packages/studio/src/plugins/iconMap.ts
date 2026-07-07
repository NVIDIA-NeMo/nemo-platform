// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { icons, type LucideIcon } from 'lucide-react';

/**
 * Converts a kebab-case icon name to PascalCase and looks it up in the
 * lucide-react `icons` record (real icons only — not helper exports like
 * the generic `Icon` component). Returns undefined if not found.
 *
 * Example: "flask-conical" → FlaskConical component
 */
export function getPluginIcon(iconName: string): LucideIcon | undefined {
  const pascalName = iconName
    .split('-')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join('');
  return (icons as Record<string, LucideIcon | undefined>)[pascalName];
}
