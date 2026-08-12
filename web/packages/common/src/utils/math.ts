// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

export const clamp = (value: number, min: number, max: number) =>
  Math.min(Math.max(value, min), max);
