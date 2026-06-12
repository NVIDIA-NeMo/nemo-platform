// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { getElapsedTime } from '@studio/routes/SafeSynthesizerJobDetailsRoute/util';

describe('getElapsedTime', () => {
  beforeEach(() => {
    // Mock current time to a fixed date for consistent testing
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2025-11-04T16:00:00.000Z'));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe('missing parameters', () => {
    it('should return null when created_at is undefined', () => {
      expect(getElapsedTime(undefined, 1800)).toBe(null);
    });

    it('should return null when created_at is empty string', () => {
      expect(getElapsedTime('', 1800)).toBe(null);
    });
  });

  describe('running job (no result summary)', () => {
    it('should calculate elapsed time from created_at to now', () => {
      // Job started 30 minutes ago (15:30:00)
      const result = getElapsedTime('2025-11-04T15:30:00.000Z');
      expect(result).toBe('00:30:00');
    });

    it('should calculate elapsed time for job started 2 hours ago', () => {
      const result = getElapsedTime('2025-11-04T14:00:00.000Z');
      expect(result).toBe('02:00:00');
    });

    it('should handle timestamps without Z suffix as UTC', () => {
      // Timestamp without Z should be treated as UTC
      // Using .000000 to avoid millisecond rounding issues
      const result = getElapsedTime('2025-11-04T15:30:00.000000');
      expect(result).toBe('00:30:00');
    });
  });

  describe('completed job (with result summary)', () => {
    it('should calculate elapsed time using total_time_sec from result summary', () => {
      // Job ran for 45 minutes (2700 seconds)
      const result = getElapsedTime('2025-11-04T15:00:00.000Z', 2700);
      expect(result).toBe('00:45:00');
    });

    it('should handle multi-hour jobs', () => {
      // Job ran for 3 hours and 15 minutes (11700 seconds)
      const result = getElapsedTime('2025-11-04T10:00:00.000Z', 11700);
      expect(result).toBe('03:15:00');
    });

    it('should handle jobs that span multiple days', () => {
      // Job ran for 26 hours, 10 minutes, 20 seconds (94220 seconds)
      const result = getElapsedTime('2025-11-03T12:00:00.000Z', 94220);
      expect(result).toBe('26:10:20');
    });

    it('should handle timestamps without Z suffix', () => {
      // Job ran for 45 minutes (2700 seconds)
      const result = getElapsedTime('2025-11-04T15:00:00.194301', 2700);
      expect(result).toBe('00:45:00');
    });
  });

  describe('UTC timestamp handling for created_at', () => {
    it('should handle timestamps with Z suffix', () => {
      // 30 minutes = 1800 seconds
      const result = getElapsedTime('2025-11-04T15:00:00.000Z', 1800);
      expect(result).toBe('00:30:00');
    });

    it('should handle timestamps without Z suffix as UTC', () => {
      // 30 minutes = 1800 seconds
      const result = getElapsedTime('2025-11-04T15:00:00.000000', 1800);
      expect(result).toBe('00:30:00');
    });

    it('should handle timestamps with positive timezone offset', () => {
      // +05:30 offset, 30 minutes = 1800 seconds
      const result = getElapsedTime('2025-11-04T15:00:00+05:30', 1800);
      expect(result).toBe('00:30:00');
    });

    it('should handle timestamps with negative timezone offset', () => {
      // -08:00 offset, 30 minutes = 1800 seconds
      const result = getElapsedTime('2025-11-04T15:00:00-08:00', 1800);
      expect(result).toBe('00:30:00');
    });

    it('should correctly parse timestamp without Z as UTC', () => {
      // Timestamp without Z should be treated as UTC, 30 minutes = 1800 seconds
      const result = getElapsedTime('2025-11-04T15:00:00.194301', 1800);
      expect(result).toBe('00:30:00');
    });
  });

  describe('edge cases', () => {
    it('should handle zero elapsed time', () => {
      const result = getElapsedTime('2025-11-04T15:00:00.000Z', 0);
      expect(result).toBe('00:00:00');
    });

    it('should handle very short elapsed time (seconds)', () => {
      // 15 seconds
      const result = getElapsedTime('2025-11-04T15:00:00.000Z', 15);
      expect(result).toBe('00:00:15');
    });

    it('should handle fractional seconds in total_time_sec', () => {
      // 1800.864 seconds = 30 minutes (fractional seconds truncated)
      const result = getElapsedTime('2025-11-04T15:00:00.123456', 1800.864);
      expect(result).toBe('00:30:00');
    });

    it('should handle negative total_time_sec (absolute difference)', () => {
      // formatElapsedTime uses Math.abs, so negative values should still work
      const result = getElapsedTime('2025-11-04T15:00:00.000Z', -1800);
      expect(result).toBe('00:30:00');
    });
  });
});
