// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { StartOption } from '@studio/components/CreateCustomizationStart/types';
import { FileJson, LayoutGrid, Plus } from 'lucide-react';

export const START_OPTIONS: StartOption[] = [
  {
    id: 'json',
    title: 'Start from a JSON config',
    description:
      'Paste or upload a job config. Anything you leave out falls back to the platform default.',
    icon: FileJson,
    enabled: true,
  },
  {
    id: 'template',
    title: 'Start from a template',
    description:
      'Pick one of your saved templates, or a ready-made NVIDIA recipe that sets the model and dataset up for you.',
    icon: LayoutGrid,
    enabled: true,
  },
  {
    id: 'scratch',
    title: 'Build from scratch',
    description: 'Open the full form with sensible defaults and choose your own model and data.',
    icon: Plus,
    enabled: true,
  },
];
