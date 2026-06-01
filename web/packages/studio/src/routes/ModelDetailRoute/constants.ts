// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

export enum ModelDetailTab {
  Card = 'card',
  Files = 'files',
}

export const isModelDetailTab = (value: string | undefined): value is ModelDetailTab =>
  Object.values(ModelDetailTab).includes(value as ModelDetailTab);
