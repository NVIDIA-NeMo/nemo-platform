// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { act, renderHook } from '@testing-library/react';

import { useLiveSeconds } from './index';

describe('useLiveSeconds', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('should update the live seconds', () => {
    const { result } = renderHook(() =>
      useLiveSeconds({ startDate: new Date('2025-01-01T00:00:00.000Z') })
    );
    // Set the system time to a known value
    vi.setSystemTime(new Date('2025-01-01T00:00:00.000Z'));

    // Initial render should calculate difference: 1 second
    expect(result.current).toBe(0);

    // Advance timers by 1 second (triggers interval + advances system time)
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(result.current).toBe(1);

    // Advance timers by 1 second (triggers interval + advances system time)
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(result.current).toBe(2);

    // Advance another second
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(result.current).toBe(3);
  });

  it('should lock the startDate value to prevent desync when startDate is provided asynchronously', () => {
    const { result, rerender } = renderHook(() =>
      useLiveSeconds({ startDate: new Date('2025-01-01T00:00:00.000Z') })
    );
    // Set the system time to a known value
    vi.setSystemTime(new Date('2025-01-01T00:00:00.000Z'));

    // Initial render
    expect(result.current).toBe(0);

    // Try to change the startDate - should be ignored (locked)
    rerender({ startDate: new Date('2025-01-01T00:00:05.000Z') });

    act(() => {
      vi.advanceTimersByTime(1000);
    });
    // Should still be calculating from original startDate (00:00:00)
    // Now at 00:00:02, so difference is 2 seconds
    expect(result.current).toBe(1);

    act(() => {
      vi.advanceTimersByTime(1000);
    });
    // Now at 00:00:03, so difference is 3 seconds
    expect(result.current).toBe(2);
  });

  it('should handle long durations', () => {
    const { result } = renderHook(() =>
      useLiveSeconds({ startDate: new Date('2025-01-01T00:00:00.000Z') })
    );
    vi.setSystemTime(new Date('2025-01-01T00:00:00.000Z'));
    for (let i = 0; i < 50; i++) {
      act(() => {
        vi.advanceTimersByTime(1000);
      });
    }
    expect(result.current).toBe(50);
  });

  it('should return undefined if startDate is not provided', () => {
    const { result } = renderHook(() => useLiveSeconds({}));
    expect(result.current).toBeUndefined();
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(result.current).toBeUndefined();
  });
});
