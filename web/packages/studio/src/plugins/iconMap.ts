// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { LucideIcon } from 'lucide-react';
import * as LucideIcons from 'lucide-react';

/**
 * Converts a kebab-case icon name to PascalCase and looks it up in lucide-react.
 * Returns undefined if the icon name is not found.
 *
 * Example: "flask-conical" → FlaskConical component
 */
export function getPluginIcon(iconName: string): LucideIcon | undefined {
  const pascalName = iconName
    .split('-')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join('');
  return (LucideIcons as unknown as Record<string, LucideIcon | undefined>)[pascalName];
}
