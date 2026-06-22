// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { formatTimeInSeconds, utcToLocalDate } from './date';

describe('formatTimeInSeconds', () => {
  it('Returns empty string when seconds is undefined', () => {
    expect(formatTimeInSeconds(undefined)).toBe('');
  });

  it('Returns the correctly-formatted time string', () => {
    expect(formatTimeInSeconds(30)).toBe('30s');
    expect(formatTimeInSeconds(60)).toBe('1m');
    expect(formatTimeInSeconds(3600)).toBe('1h');
    expect(formatTimeInSeconds(3600 + 60)).toBe('1h 1m');
    expect(formatTimeInSeconds(3600 + 60 + 30)).toBe('1h 1m 30s');
    expect(formatTimeInSeconds(3600 * 25)).toBe('25h');
  });
});

describe('utcToLocalDate', () => {
  it('Returns undefined when input is undefined', () => {
    expect(utcToLocalDate(undefined)).toBeUndefined();
  });

  it('Returns undefined when input is an empty string', () => {
    expect(utcToLocalDate('')).toBeUndefined();
  });

  it('Returns undefined for invalid date strings', () => {
    expect(utcToLocalDate('not-a-date')).toBeUndefined();
    expect(utcToLocalDate('2025-13-45T99:99:99')).toBeUndefined();
  });

  it('Converts UTC ISO string without timezone indicator to Date', () => {
    const result = utcToLocalDate('2025-11-17T21:53:35.903780');
    expect(result).toBeInstanceOf(Date);
    expect(result?.toISOString()).toBe('2025-11-17T21:53:35.903Z');
  });

  it('Converts UTC ISO string with Z timezone indicator to Date', () => {
    const result = utcToLocalDate('2025-11-17T21:53:35.903780Z');
    expect(result).toBeInstanceOf(Date);
    expect(result?.toISOString()).toBe('2025-11-17T21:53:35.903Z');
  });

  it('Handles UTC ISO string with timezone offset', () => {
    const result = utcToLocalDate('2025-11-17T21:53:35.903780+00:00');
    expect(result).toBeInstanceOf(Date);
    expect(result?.toISOString()).toBe('2025-11-17T21:53:35.903Z');
  });

  it('Preserves timezone offset in the conversion', () => {
    // A date with +05:00 offset should be 5 hours earlier in UTC
    const result = utcToLocalDate('2025-11-17T21:53:35+05:00');
    expect(result).toBeInstanceOf(Date);
    expect(result?.toISOString()).toBe('2025-11-17T16:53:35.000Z');
  });

  it('Handles various ISO string formats', () => {
    // Without milliseconds
    const result1 = utcToLocalDate('2025-11-17T21:53:35');
    expect(result1?.toISOString()).toBe('2025-11-17T21:53:35.000Z');

    // With milliseconds
    const result2 = utcToLocalDate('2025-11-17T21:53:35.123');
    expect(result2?.toISOString()).toBe('2025-11-17T21:53:35.123Z');

    // With microseconds (JavaScript will truncate to milliseconds)
    const result3 = utcToLocalDate('2025-11-17T21:53:35.123456');
    expect(result3?.toISOString()).toBe('2025-11-17T21:53:35.123Z');
  });
});
