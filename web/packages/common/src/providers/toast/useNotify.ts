// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { NotifyFn } from '@nemo/common/src/providers/toast/types';
import { ToastContext } from '@nemo/common/src/providers/toast/useToast';
import { logger } from '@nemo/common/src/utils/logger';
import { useCallback, useContext } from 'react';

/**
 * Resolves a notification sink: an explicit `onNotify` first, then the
 * ToastProvider above this component. Unlike `useToast` this never throws —
 * a plugin renders against a different `ToastContext` instance than the one
 * Studio mounts, so the context is legitimately absent there.
 */
export const useNotify = (onNotify?: NotifyFn): NotifyFn => {
  const toast = useContext(ToastContext)?.toast;

  return useCallback(
    (message, type = 'info', options) => {
      if (onNotify) {
        onNotify(message, type, options);
        return;
      }
      if (toast) {
        toast[type](message, options);
        return;
      }
      logger.warn(`[toast] dropped notification, no ToastProvider and no onNotify: ${message}`);
    },
    [onNotify, toast]
  );
};
