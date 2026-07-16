// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import YAML from 'yaml';

/**
 * Parses a user-supplied NAT workflow config (YAML or JSON text) into the dict
 * the agents API stores as `config`. Validates enough to catch paste mistakes
 * early: it must parse to an object and carry a top-level `workflow` section.
 * Deep NAT validation only happens at deploy time, so we stay intentionally
 * light here and surface a clear message instead.
 */
export const parseAgentConfig = (text: string): Record<string, unknown> => {
  const trimmed = text.trim();
  if (!trimmed) {
    throw new Error('Paste your NAT workflow config to register an agent.');
  }

  let parsed: unknown;
  try {
    parsed = YAML.parse(trimmed);
  } catch (err) {
    throw new Error(`Config is not valid YAML: ${(err as Error).message}`);
  }

  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('Config must be a YAML mapping (a NAT workflow config).');
  }

  const config = parsed as Record<string, unknown>;
  if (!('workflow' in config)) {
    throw new Error(
      "Config is missing a top-level 'workflow' section — this is not a NAT workflow."
    );
  }

  return config;
};
