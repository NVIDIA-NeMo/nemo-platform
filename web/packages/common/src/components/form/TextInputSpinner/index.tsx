// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Spinner } from '@nvidia/foundations-react-core';

/**
 * A spinner that is used to indicate that a text input is loading
 * Slotted in slotEnd
 */
export const TextInputSpinner = () => {
  return <Spinner aria-label="Loading" size="small" className="[&>div]:contents" />;
};
