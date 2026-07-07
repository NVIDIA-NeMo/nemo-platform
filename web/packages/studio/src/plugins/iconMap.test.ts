// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { getPluginIcon } from '@studio/plugins/iconMap';

describe('getPluginIcon', () => {
  it('returns a known Lucide component for a valid kebab-case name', () => {
    const icon = getPluginIcon('flask-conical');
    expect(icon).toBeDefined();
    // Lucide components may be objects or functions depending on the version
    expect(icon).toBeTruthy();
  });

  it('returns a known single-word icon', () => {
    const icon = getPluginIcon('settings');
    expect(icon).toBeDefined();
  });

  it('returns undefined for an unknown icon name', () => {
    expect(getPluginIcon('this-icon-does-not-exist')).toBeUndefined();
  });

  it('returns undefined for an empty string', () => {
    expect(getPluginIcon('')).toBeUndefined();
  });

  it('returns undefined for a name with a trailing hyphen', () => {
    expect(getPluginIcon('flask-')).toBeUndefined();
  });
});
