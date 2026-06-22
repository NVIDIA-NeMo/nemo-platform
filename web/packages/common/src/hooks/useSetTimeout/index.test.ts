// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { act, renderHook } from '@testing-library/react';

import { useSetTimeout } from './index';

describe('useSetTimeout', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('should execute callback after the specified delay', () => {
    const callback = vi.fn();
    const { result } = renderHook(() => useSetTimeout());
    const [setTimeout] = result.current;

    act(() => {
      setTimeout(callback, 1000);
    });

    expect(callback).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(1000);
    });

    expect(callback).toHaveBeenCalledTimes(1);
  });

  it('should cleanup timeout on unmount', () => {
    const callback = vi.fn();
    const { result, unmount } = renderHook(() => useSetTimeout());
    const [setTimeout] = result.current;

    act(() => {
      setTimeout(callback, 1000);
    });

    unmount();

    act(() => {
      vi.advanceTimersByTime(1000);
    });

    expect(callback).not.toHaveBeenCalled();
  });

  it('should allow manual clearing of timeout', () => {
    const callback = vi.fn();
    const { result } = renderHook(() => useSetTimeout());
    const [setTimeout, clearTimeout] = result.current;

    act(() => {
      setTimeout(callback, 1000);
    });

    act(() => {
      clearTimeout();
    });

    act(() => {
      vi.advanceTimersByTime(1000);
    });

    expect(callback).not.toHaveBeenCalled();
  });

  it('should clear previous timeout when setTimeout is called multiple times', () => {
    const callback1 = vi.fn();
    const callback2 = vi.fn();
    const { result } = renderHook(() => useSetTimeout());
    const [setTimeout] = result.current;

    act(() => {
      setTimeout(callback1, 1000);
    });

    act(() => {
      setTimeout(callback2, 2000);
    });

    act(() => {
      vi.advanceTimersByTime(1000);
    });

    expect(callback1).not.toHaveBeenCalled();
    expect(callback2).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(1000);
    });

    expect(callback1).not.toHaveBeenCalled();
    expect(callback2).toHaveBeenCalledTimes(1);
  });

  it('should handle zero delay correctly', () => {
    const callback = vi.fn();
    const { result } = renderHook(() => useSetTimeout());
    const [setTimeout] = result.current;

    act(() => {
      setTimeout(callback, 0);
    });

    expect(callback).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(0);
    });

    expect(callback).toHaveBeenCalledTimes(1);
  });

  it('should allow multiple independent hook instances', () => {
    const callback1 = vi.fn();
    const callback2 = vi.fn();

    const { result: result1 } = renderHook(() => useSetTimeout());
    const { result: result2 } = renderHook(() => useSetTimeout());

    const [setTimeout1] = result1.current;
    const [setTimeout2] = result2.current;

    act(() => {
      setTimeout1(callback1, 1000);
      setTimeout2(callback2, 2000);
    });

    act(() => {
      vi.advanceTimersByTime(1000);
    });

    expect(callback1).toHaveBeenCalledTimes(1);
    expect(callback2).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(1000);
    });

    expect(callback1).toHaveBeenCalledTimes(1);
    expect(callback2).toHaveBeenCalledTimes(1);
  });

  it('should allow callback to access component state', () => {
    const { result } = renderHook(() => {
      const [setTimeout] = useSetTimeout();
      const value = 'test-value';
      return { setTimeout, value };
    });

    const capturedValues: string[] = [];
    const callback = () => {
      capturedValues.push(result.current.value);
    };

    act(() => {
      result.current.setTimeout(callback, 1000);
    });

    act(() => {
      vi.advanceTimersByTime(1000);
    });

    expect(capturedValues).toEqual(['test-value']);
  });

  it('should safely handle clearing non-existent timeout', () => {
    const { result } = renderHook(() => useSetTimeout());
    const [, clearTimeout] = result.current;

    expect(() => {
      act(() => {
        clearTimeout();
      });
    }).not.toThrow();
  });

  it('should allow setTimeout to be called after clearing', () => {
    const callback1 = vi.fn();
    const callback2 = vi.fn();
    const { result } = renderHook(() => useSetTimeout());
    const [setTimeout, clearTimeout] = result.current;

    act(() => {
      setTimeout(callback1, 1000);
    });

    act(() => {
      clearTimeout();
    });

    act(() => {
      setTimeout(callback2, 1000);
    });

    act(() => {
      vi.advanceTimersByTime(1000);
    });

    expect(callback1).not.toHaveBeenCalled();
    expect(callback2).toHaveBeenCalledTimes(1);
  });

  it('should support chaining timeouts in callback', () => {
    const callback1 = vi.fn();
    const callback2 = vi.fn();
    const { result } = renderHook(() => useSetTimeout());
    const [setTimeout] = result.current;

    act(() => {
      setTimeout(() => {
        callback1();
        setTimeout(callback2, 1000);
      }, 1000);
    });

    act(() => {
      vi.advanceTimersByTime(1000);
    });

    expect(callback1).toHaveBeenCalledTimes(1);
    expect(callback2).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(1000);
    });

    expect(callback2).toHaveBeenCalledTimes(1);
  });
});
