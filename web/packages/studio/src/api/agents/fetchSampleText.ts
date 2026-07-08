// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { BASE_URL } from '@studio/constants/environment';

/**
 * Fetches a static asset from the public directory (by path relative to public/)
 * and returns its text. Shared primitive for sample-agent assets: the create flow
 * parses the returned YAML; the eval flow seeds the returned text into a fileset.
 */
export const fetchSampleText = async (path: string): Promise<string> => {
  const baseUrl = BASE_URL.replace(/\/$/, '');
  const response = await fetch(`${baseUrl}/${path}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch ${path}: ${response.statusText}`);
  }
  return response.text();
};
