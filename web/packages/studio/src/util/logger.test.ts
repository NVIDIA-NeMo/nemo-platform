// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

const { mockEmit } = vi.hoisted(() => ({
  mockEmit: vi.fn(),
}));

vi.mock('@opentelemetry/api-logs', () => {
  const SeverityNumber = {
    DEBUG: 5,
    INFO: 9,
    WARN: 13,
    ERROR: 17,
  };
  return {
    SeverityNumber,
    logs: {
      getLogger: () => ({
        emit: mockEmit,
      }),
    },
  };
});

vi.mock('@studio/constants/environment', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@studio/constants/environment')>();
  return {
    ...actual,
    OTEL_SERVICE_NAME: 'test-service',
    VERSION_SHA: 'abc123',
  };
});

import { SeverityNumber } from '@opentelemetry/api-logs';
import { handleGenericError, logVersion, websiteLogger } from '@studio/util/logger';

describe('WebsiteLogger', () => {
  beforeEach(() => {
    mockEmit.mockClear();
  });

  it('should log debug messages to console.debug and otel', () => {
    const spy = vi.spyOn(console, 'debug').mockImplementation(() => {});
    // eslint-disable-next-line testing-library/no-debugging-utils
    websiteLogger.debug('debug msg');
    expect(spy).toHaveBeenCalledWith('debug msg');
    expect(mockEmit).toHaveBeenCalledWith({
      severityNumber: SeverityNumber.DEBUG,
      body: 'debug msg',
    });
    spy.mockRestore();
  });

  it('should log info messages to console.info and otel', () => {
    const spy = vi.spyOn(console, 'info').mockImplementation(() => {});
    websiteLogger.info('info msg');
    expect(spy).toHaveBeenCalledWith('info msg');
    expect(mockEmit).toHaveBeenCalledWith({
      severityNumber: SeverityNumber.INFO,
      body: 'info msg',
    });
    spy.mockRestore();
  });

  it('should log warn messages to console.warn and otel', () => {
    const spy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    websiteLogger.warn('warn msg');
    expect(spy).toHaveBeenCalledWith('warn msg');
    expect(mockEmit).toHaveBeenCalledWith({
      severityNumber: SeverityNumber.WARN,
      body: 'warn msg',
    });
    spy.mockRestore();
  });

  it('should log error messages to console.error and otel', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    websiteLogger.error('error msg');
    expect(spy).toHaveBeenCalledWith('error msg');
    expect(mockEmit).toHaveBeenCalledWith({
      severityNumber: SeverityNumber.ERROR,
      body: 'error msg',
    });
    spy.mockRestore();
  });
});

describe('handleGenericError', () => {
  beforeEach(() => {
    mockEmit.mockClear();
  });

  it('should stringify Error objects before logging', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const error = new Error('test error');
    handleGenericError(error);
    expect(spy).toHaveBeenCalledWith(JSON.stringify(error));
    spy.mockRestore();
  });

  it('should log string errors directly', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    handleGenericError('string error');
    expect(spy).toHaveBeenCalledWith('string error');
    spy.mockRestore();
  });
});

describe('logVersion', () => {
  it('should log version when VERSION_SHA is set', async () => {
    const spy = vi.spyOn(console, 'info').mockImplementation(() => {});
    await logVersion();
    expect(spy).toHaveBeenCalledWith('Version: abc123');
    spy.mockRestore();
  });
});
