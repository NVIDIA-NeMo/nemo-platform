// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { SafeSynthesizerJob } from '@nemo/sdk/generated/safe-synthesizer/schema';
import { isCancellableJob } from '@studio/routes/SafeSynthesizerListRoute/utils';

describe('SafeSynthesizerListRoute utils', () => {
  describe('isCancellableJob', () => {
    it('should return true for "created" status', () => {
      const status: SafeSynthesizerJob['status'] = 'created';
      expect(isCancellableJob(status)).toBe(true);
    });

    it('should return true for "pending" status', () => {
      const status: SafeSynthesizerJob['status'] = 'pending';
      expect(isCancellableJob(status)).toBe(true);
    });

    it('should return true for "active" status', () => {
      const status: SafeSynthesizerJob['status'] = 'active';
      expect(isCancellableJob(status)).toBe(true);
    });

    it('should return false for "completed" status', () => {
      const status: SafeSynthesizerJob['status'] = 'completed';
      expect(isCancellableJob(status)).toBe(false);
    });

    it('should return false for "error" status', () => {
      const status: SafeSynthesizerJob['status'] = 'error';
      expect(isCancellableJob(status)).toBe(false);
    });

    it('should return false for "cancelled" status', () => {
      const status: SafeSynthesizerJob['status'] = 'cancelled';
      expect(isCancellableJob(status)).toBe(false);
    });

    it('should return false for "cancelling" status', () => {
      const status: SafeSynthesizerJob['status'] = 'cancelling';
      expect(isCancellableJob(status)).toBe(false);
    });
  });
});
