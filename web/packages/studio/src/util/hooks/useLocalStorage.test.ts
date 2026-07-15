// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useLocalStorage } from '@studio/util/hooks/useLocalStorage';
import { renderHook, act } from '@testing-library/react';

describe('useLocalStorage', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('returns default value when no stored value exists', () => {
    const { result } = renderHook(() => useLocalStorage('test-key', 'default'));
    expect(result.current[0]).toBe('default');
  });

  it('returns undefined when no default and no stored value', () => {
    const { result } = renderHook(() => useLocalStorage('test-key'));
    expect(result.current[0]).toBeUndefined();
  });

  it('reads existing value from localStorage', () => {
    localStorage.setItem('test-key', JSON.stringify('stored-value'));
    const { result } = renderHook(() => useLocalStorage('test-key', 'default'));
    expect(result.current[0]).toBe('stored-value');
  });

  it('setValue updates state and localStorage', () => {
    const { result } = renderHook(() => useLocalStorage<string>('test-key', 'initial'));

    act(() => {
      result.current[1]('updated');
    });

    expect(result.current[0]).toBe('updated');
    expect(localStorage.getItem('test-key')).toBe(JSON.stringify('updated'));
  });

  it('deleteValue removes from state and localStorage', () => {
    localStorage.setItem('test-key', JSON.stringify('to-delete'));
    const { result } = renderHook(() => useLocalStorage<string>('test-key', 'default'));

    expect(result.current[0]).toBe('to-delete');

    act(() => {
      result.current[2]();
    });

    // With no stored value, the snapshot falls back to the default.
    expect(result.current[0]).toBe('default');
    expect(localStorage.getItem('test-key')).toBeNull();
  });

  it('handles objects as values', () => {
    const obj = { name: 'test', count: 42 };
    const { result } = renderHook(() => useLocalStorage<typeof obj>('obj-key'));

    act(() => {
      result.current[1](obj);
    });

    expect(result.current[0]).toEqual(obj);
    expect(JSON.parse(localStorage.getItem('obj-key')!)).toEqual(obj);
  });

  it('falls back to default when localStorage has invalid JSON', () => {
    localStorage.setItem('bad-key', 'not-json{');

    // SyntaxError from JSON.parse is caught → returns defaultValue
    const { result } = renderHook(() => useLocalStorage('bad-key', 'fallback'));

    expect(result.current[0]).toBe('fallback');
  });

  it('reacts to storage events from other tabs', () => {
    const { result } = renderHook(() => useLocalStorage<string>('test-key', 'default'));
    expect(result.current[0]).toBe('default');

    act(() => {
      // Simulate another tab writing the key. `storage` events don't touch this tab's
      // localStorage automatically, so set the value first.
      localStorage.setItem('test-key', JSON.stringify('from-other-tab'));
      window.dispatchEvent(new StorageEvent('storage', { key: 'test-key' }));
    });

    expect(result.current[0]).toBe('from-other-tab');
  });

  it('keeps two hooks on the same key in sync within a tab', () => {
    const { result: a } = renderHook(() => useLocalStorage<string>('shared', 'default'));
    const { result: b } = renderHook(() => useLocalStorage<string>('shared', 'default'));

    act(() => {
      a.current[1]('written-by-a');
    });

    expect(a.current[0]).toBe('written-by-a');
    expect(b.current[0]).toBe('written-by-a');
  });

  it('returns a stable reference across re-renders when the value is unchanged', () => {
    localStorage.setItem('obj-key', JSON.stringify({ a: 1 }));
    const { result, rerender } = renderHook(() => useLocalStorage<{ a: number }>('obj-key'));

    const first = result.current[0];
    rerender();
    expect(result.current[0]).toBe(first);
  });

  it('does not loop when the default value is a fresh reference each render', () => {
    // A callsite passing an inline `[]` produces a new default reference every render.
    // The snapshot must stay stable to avoid the "getSnapshot should be cached" loop.
    const { result, rerender } = renderHook(() => useLocalStorage<string[]>('missing-key', []));

    const first = result.current[0];
    rerender();
    expect(result.current[0]).toBe(first);
    expect(result.current[0]).toEqual([]);
  });
});
