// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  enhanceClickSpanName,
  enhanceFetchSpanName,
  enhanceNavigationSpanName,
  enhanceSubmitSpanName,
  enhanceXhrSpanName,
  hrTimeToMilliseconds,
} from '@studio/telemetry/util';

describe('hrTimeToMilliseconds', () => {
  it('converts [seconds, nanoseconds] to milliseconds', () => {
    expect(hrTimeToMilliseconds([1, 500_000_000])).toBe(1500);
  });

  it('handles zero', () => {
    expect(hrTimeToMilliseconds([0, 0])).toBe(0);
  });

  it('rounds nanoseconds', () => {
    expect(hrTimeToMilliseconds([0, 1_500_000])).toBe(2);
  });
});

describe('enhanceFetchSpanName', () => {
  it('includes method and url pathname', () => {
    const result = enhanceFetchSpanName('HTTP GET', { 'http.url': 'https://api.test/v1/models' });
    expect(result).toBe('FETCH GET /v1/models');
  });

  it('uses url.full attribute as fallback', () => {
    const result = enhanceFetchSpanName('HTTP POST', {
      'url.full': 'https://api.test/v1/jobs',
    });
    expect(result).toBe('FETCH POST /v1/jobs');
  });

  it('omits path when url is not a valid URL', () => {
    const result = enhanceFetchSpanName('HTTP GET', { 'http.url': 'not-a-url' });
    expect(result).toBe('FETCH GET');
  });

  it('omits path when no url attribute', () => {
    const result = enhanceFetchSpanName('HTTP GET', {});
    expect(result).toBe('FETCH GET');
  });
});

describe('enhanceXhrSpanName', () => {
  it('includes method and url pathname', () => {
    const result = enhanceXhrSpanName('GET', { 'http.url': 'https://api.test/v1/data' });
    expect(result).toBe('XHR GET /v1/data');
  });

  it('omits path when url is not valid', () => {
    const result = enhanceXhrSpanName('POST', {});
    expect(result).toBe('XHR POST');
  });
});

describe('enhanceClickSpanName', () => {
  it('returns "Click" with no attributes', () => {
    expect(enhanceClickSpanName({})).toBe('Click');
  });

  it('adds tag name and id', () => {
    const result = enhanceClickSpanName({
      event_target_tag_name: 'BUTTON',
      event_target_id: 'submit-btn',
    });
    expect(result).toBe('Click on button#submit-btn');
  });

  it('uses class when no id', () => {
    const result = enhanceClickSpanName({
      event_target_tag_name: 'DIV',
      event_target_class: 'card primary',
    });
    expect(result).toBe('Click on div.card');
  });

  it('uses text when no id or class', () => {
    const result = enhanceClickSpanName({
      event_target_tag_name: 'SPAN',
      event_target_text: 'Save',
    });
    expect(result).toBe('Click on span "Save"');
  });

  it('truncates long text', () => {
    const longText = 'A'.repeat(50);
    const result = enhanceClickSpanName({
      event_target_tag_name: 'SPAN',
      event_target_text: longText,
    });
    expect(result).toContain('...');
    expect(result.length).toBeLessThan(60);
  });

  it('falls back to target_element when no tag name', () => {
    const result = enhanceClickSpanName({ target_element: 'custom-el' });
    expect(result).toBe('Click on custom-el');
  });

  it('uses target_ prefixed attributes as fallback', () => {
    const result = enhanceClickSpanName({
      target_tag_name: 'A',
      target_id: 'link',
    });
    expect(result).toBe('Click on a#link');
  });
});

describe('enhanceNavigationSpanName', () => {
  it('returns Navigation', () => {
    expect(enhanceNavigationSpanName()).toBe('Navigation');
  });
});

describe('enhanceSubmitSpanName', () => {
  it('returns basic Form Submit with no attributes', () => {
    expect(enhanceSubmitSpanName({})).toBe('Form Submit');
  });

  it('adds target id', () => {
    expect(enhanceSubmitSpanName({ event_target_id: 'login-form' })).toBe(
      'Form Submit #login-form'
    );
  });

  it('falls back to target_element', () => {
    expect(enhanceSubmitSpanName({ event_target_element: 'form.search' })).toBe(
      'Form Submit form.search'
    );
  });
});
