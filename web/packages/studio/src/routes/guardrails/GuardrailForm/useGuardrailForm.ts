// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { GuardrailFormContext } from '@studio/routes/guardrails/GuardrailForm/context';
import { useContext } from 'react';

export const useGuardrailForm = () => {
  const context = useContext(GuardrailFormContext);
  if (!context) {
    throw new Error('useGuardrailForm must be used within a GuardrailFormProvider');
  }
  return context;
};
