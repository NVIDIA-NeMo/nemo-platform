// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

package cmd

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"sync/atomic"
	"time"

	"go.opentelemetry.io/contrib/bridges/otelslog"
	"go.opentelemetry.io/contrib/exporters/autoexport"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/exporters/otlp/otlplog/otlploghttp"
	"go.opentelemetry.io/otel/exporters/stdout/stdoutlog"
	"go.opentelemetry.io/otel/log/global"
	"go.opentelemetry.io/otel/sdk/log"
	"go.opentelemetry.io/otel/sdk/resource"
)

const (
	name                     = "nmp.nvidia.com/nemo-platform/jobs-launcher"
	NEMO_JOB_WORKSPACE       = "NEMO_JOB_WORKSPACE"
	NEMO_JOB_ID_ENV          = "NEMO_JOB_ID"
	NEMO_JOB_ATTEMPT_ID_ENV  = "NEMO_JOB_ATTEMPT_ID"
	NEMO_JOB_STEP_NAME_ENV   = "NEMO_JOB_STEP"
	NEMO_JOB_TASK_ID_ENV     = "NEMO_JOB_TASK"
	nmpJobLogsEndpointEnv    = "NMP_JOB_LOGS_ENDPOINT"
	otlpHTTPLogExportTimeout = 10 * time.Second
)

var (
	workspaceID = os.Getenv(NEMO_JOB_WORKSPACE)
	jobID       = os.Getenv(NEMO_JOB_ID_ENV)
	attemptID   = os.Getenv(NEMO_JOB_ATTEMPT_ID_ENV)
	step        = os.Getenv(NEMO_JOB_STEP_NAME_ENV)
	taskID      = os.Getenv(NEMO_JOB_TASK_ID_ENV)
)

// setupOTELSDK bootstraps the OpenTelemetry pipeline.
// If it does not return an error, make sure to call shutdown for proper cleanup.
// Returns the shutdown function, logger provider, and any error encountered.
func setupOTELSDK(ctx context.Context) (func(context.Context) error, *log.LoggerProvider, error) {
	var shutdownFuncs []func(context.Context) error

	// shutdown calls cleanup functions registered via shutdownFuncs.
	// The errors from the calls are joined.
	// Each registered cleanup will be invoked once.
	shutdown := func(ctx context.Context) error {
		var err error
		for _, fn := range shutdownFuncs {
			err = errors.Join(err, fn(ctx))
		}
		shutdownFuncs = nil
		return err
	}

	// Create a resource to include all OTEL attributes.
	res, err := resource.Merge(
		resource.Default(),
		// Ensure our job metadata is included in the resource.
		resource.NewSchemaless(
			attribute.String("workspace", workspaceID),
			attribute.String("job", jobID),
			attribute.String("job_attempt", attemptID),
			attribute.String("job_step", step),
			attribute.String("job_task", taskID),
		),
	)
	if err != nil {
		return shutdown, nil, err
	}

	// handleErr calls shutdown for cleanup and makes sure that all errors are returned.
	handleErr := func(inErr error) {
		err = errors.Join(inErr, shutdown(ctx))
	}

	// Set up logger provider.
	loggerProvider, err := newLoggerProvider(ctx, res)
	if err != nil {
		handleErr(err)
		return shutdown, nil, err
	}
	shutdownFuncs = append(shutdownFuncs, loggerProvider.Shutdown)
	global.SetLoggerProvider(loggerProvider)

	// Set default slog provider bridge.
	slog.SetDefault(otelslog.NewLogger(name, otelslog.WithLoggerProvider(loggerProvider)))

	return shutdown, loggerProvider, err
}

// newLoggerProvider creates a new OTEL logger provider with the given resource.
func newLoggerProvider(ctx context.Context, res *resource.Resource) (*log.LoggerProvider, error) {
	logExporter, err := newLogExporter(ctx)
	if err != nil {
		return nil, err
	}

	loggerProvider := log.NewLoggerProvider(
		log.WithProcessor(log.NewBatchProcessor(logExporter)),
		log.WithResource(res),
	)
	return loggerProvider, nil
}

func newLogExporter(ctx context.Context) (log.Exporter, error) {
	if endpoint := os.Getenv(nmpJobLogsEndpointEnv); endpoint != "" {
		if os.Getenv(workloadIdentityTokenFileEnv) != "" {
			tokenSource, err := newOTLPLogWorkloadAuthTokenSource(ctx)
			if err != nil {
				return nil, fmt.Errorf("configure workload identity auth for OTLP logs: %w", err)
			}
			return newRefreshableAuthLogExporter(ctx, endpoint, tokenSource, otlpHTTPLogExporter)
		}
		return otlploghttp.New(ctx, otlploghttp.WithEndpointURL(endpoint))
	}

	return autoexport.NewLogExporter(
		ctx,
		// Default to a stdout log exporter if autoexport fails to configure one.
		autoexport.WithFallbackLogExporter(
			func(ctx context.Context) (log.Exporter, error) {
				return stdoutlog.New()
			},
		),
	)
}

type authHeaderSource interface {
	AuthorizationHeader(context.Context) (string, error)
}

type logExporterFactory func(context.Context, ...otlploghttp.Option) (log.Exporter, error)

type refreshableAuthLogExporter struct {
	exporter log.Exporter
	stopped  atomic.Bool
}

func newRefreshableAuthLogExporter(
	ctx context.Context,
	endpoint string,
	authSource authHeaderSource,
	newExporter logExporterFactory,
) (log.Exporter, error) {
	if _, err := authSource.AuthorizationHeader(ctx); err != nil {
		return nil, fmt.Errorf("configure workload identity auth for OTLP logs: %w", err)
	}

	exporter, err := newExporter(
		ctx,
		otlploghttp.WithEndpointURL(endpoint),
		otlploghttp.WithHTTPClient(&http.Client{
			Transport: &authHeaderTransport{source: authSource},
			Timeout:   otlpHTTPLogExportTimeout,
		}),
	)
	if err != nil {
		return nil, err
	}
	return &refreshableAuthLogExporter{exporter: exporter}, nil
}

func (e *refreshableAuthLogExporter) Export(ctx context.Context, records []log.Record) error {
	if e.stopped.Load() {
		return nil
	}

	return e.exporter.Export(ctx, records)
}

func (e *refreshableAuthLogExporter) Shutdown(ctx context.Context) error {
	if e.stopped.Swap(true) {
		return nil
	}
	return e.exporter.Shutdown(ctx)
}

func (e *refreshableAuthLogExporter) ForceFlush(ctx context.Context) error {
	return e.exporter.ForceFlush(ctx)
}

type authHeaderTransport struct {
	source authHeaderSource
	base   http.RoundTripper
}

func (t *authHeaderTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	authHeader, err := t.source.AuthorizationHeader(req.Context())
	if err != nil {
		return nil, fmt.Errorf("refresh workload identity auth for OTLP logs: %w", err)
	}

	clonedReq := req.Clone(req.Context())
	clonedReq.Header = req.Header.Clone()
	clonedReq.Header.Set("Authorization", authHeader)
	return t.baseTransport().RoundTrip(clonedReq)
}

func (t *authHeaderTransport) baseTransport() http.RoundTripper {
	if t.base != nil {
		return t.base
	}
	return http.DefaultTransport
}

func otlpHTTPLogExporter(ctx context.Context, opts ...otlploghttp.Option) (log.Exporter, error) {
	return otlploghttp.New(ctx, opts...)
}
