// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/** Display message from an unknown error; falls back when it is not an Error. */
export function getErrorMessage(error: unknown, defaultMessage?: string): string {
  return error instanceof Error
    ? error.message
    : (defaultMessage ?? 'Something went wrong. Please try again.');
}
