// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/* eslint-disable no-console */
import { Logger, logs, SeverityNumber } from '@opentelemetry/api-logs';
import { OTEL_SERVICE_NAME, VERSION_SHA } from '@studio/constants/environment';

const otelLogger: Logger = logs.getLogger(OTEL_SERVICE_NAME);

/**
 * Wrapper class around the global OpenTelemetry Logger. Logs will be transported to:
 * 1. The console
 * 2. OpenTelemetry Collector (except in local and test envs - see `telemetry.ts`)
 *
 * We export a global instance of this class below (`websiteLogger`). That variable
 * should be used by individual modules, in-place of `console.log`.
 *
 * Example usage:
 *
 * ```
 * import { websiteLogger } from '@studio/util/logger';
 * websiteLogger.info('Some message to log');
 * ```
 */
class WebsiteLogger {
  private log(level: SeverityNumber, message: string, cause?: unknown) {
    const logArgs: [string, ...unknown[]] = cause !== undefined ? [message, cause] : [message];
    if (level === SeverityNumber.ERROR) console.error(...logArgs);
    else if (level === SeverityNumber.WARN) console.warn(...logArgs);
    else if (level === SeverityNumber.INFO) console.info(...logArgs);
    else if (level === SeverityNumber.DEBUG) console.debug(...logArgs);

    const attributes: Record<string, string> = {};
    if (cause instanceof Error) {
      if (cause.message) attributes['error.message'] = cause.message;
      if (cause.stack) attributes['error.stack'] = cause.stack;
    } else if (cause !== undefined) {
      attributes['error'] = String(cause);
    }

    otelLogger.emit({
      severityNumber: level,
      body: message,
      ...(Object.keys(attributes).length > 0 && { attributes }),
    });
  }

  debug(message: string, cause?: unknown) {
    this.log(SeverityNumber.DEBUG, message, cause);
  }

  error(message: string, cause?: unknown) {
    this.log(SeverityNumber.ERROR, message, cause);
  }

  info(message: string, cause?: unknown) {
    this.log(SeverityNumber.INFO, message, cause);
  }

  warn(message: string, cause?: unknown) {
    this.log(SeverityNumber.WARN, message, cause);
  }
}

// Global instance of our logger that should be used by individual modules, in-place of `console.log`.
export const logger = new WebsiteLogger();

/**
 * Converts a unknown error to an Error object.
 */
export function toError(err: unknown): Error {
  return err instanceof Error ? err : new Error(String(err));
}

/**
 * Handles a generic error by logging it to the website logger.
 */
export const handleGenericError = (error: Error | string) => {
  if (error instanceof Error) {
    logger.error(error.message, error);
  } else {
    logger.error(error);
  }
};

/**
 * Logs the version of the app to the website logger.
 */
export const logVersion = async () => {
  if (VERSION_SHA) {
    logger.info(`Version: ${VERSION_SHA}`);
  }
};
