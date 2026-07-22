// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

package cmd

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"strings"
	"sync/atomic"
	"time"

	"github.com/NVIDIA-NeMo/nemo-platform/services/core/jobs/jobs-launcher/nmpclient"
	"go.opentelemetry.io/contrib/bridges/otelslog"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/exporters/otlp/otlplog/otlploghttp"
	"go.opentelemetry.io/otel/exporters/stdout/stdoutlog"
	"go.opentelemetry.io/otel/log/global"
	"go.opentelemetry.io/otel/sdk/log"
	"go.opentelemetry.io/otel/sdk/resource"
)

const (
	name                    = "nmp.nvidia.com/nemo-platform/jobs-launcher"
	NEMO_JOB_WORKSPACE      = "NEMO_JOB_WORKSPACE"
	NEMO_JOB_ID_ENV         = "NEMO_JOB_ID"
	NEMO_JOB_ATTEMPT_ID_ENV = "NEMO_JOB_ATTEMPT_ID"
	NEMO_JOB_STEP_NAME_ENV  = "NEMO_JOB_STEP"
	NEMO_JOB_TASK_ID_ENV    = "NEMO_JOB_TASK"

	launcherLogsExporterEnv     = "NMP_JOB_LAUNCHER_LOGS_EXPORTER"
	launcherOTLPLogsEndpointEnv = "NMP_JOB_LAUNCHER_OTLP_LOGS_ENDPOINT"
	launcherOTLPLogsHeadersEnv  = "NMP_JOB_LAUNCHER_OTLP_LOGS_HEADERS"
	launcherOTLPLogsProtocolEnv = "NMP_JOB_LAUNCHER_OTLP_LOGS_PROTOCOL"
	launcherOTLPLogsTimeoutEnv  = "NMP_JOB_LAUNCHER_OTLP_LOGS_TIMEOUT"
	launcherOTLPLogsCompressEnv = "NMP_JOB_LAUNCHER_OTLP_LOGS_COMPRESSION"
	launcherOTLPHTTPProto       = "http/protobuf"
	defaultLauncherLogsExporter = "console"
	otlpHTTPLogExportTimeout    = 10 * time.Second
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
	switch strings.ToLower(strings.TrimSpace(os.Getenv(launcherLogsExporterEnv))) {
	case "", defaultLauncherLogsExporter, "stdout":
		return stdoutlog.New()
	case "none":
		return noopLogExporter{}, nil
	case "otlp":
		return newLauncherOTLPLogExporter(ctx)
	default:
		return nil, fmt.Errorf("unsupported %s value %q", launcherLogsExporterEnv, os.Getenv(launcherLogsExporterEnv))
	}
}

func newLauncherOTLPLogExporter(ctx context.Context) (log.Exporter, error) {
	protocol := strings.TrimSpace(os.Getenv(launcherOTLPLogsProtocolEnv))
	if protocol == "" {
		protocol = launcherOTLPHTTPProto
	}
	if protocol != launcherOTLPHTTPProto {
		return nil, fmt.Errorf("%s must be %q, got %q", launcherOTLPLogsProtocolEnv, launcherOTLPHTTPProto, protocol)
	}

	endpointURL := strings.TrimSpace(os.Getenv(launcherOTLPLogsEndpointEnv))
	if endpointURL == "" {
		return nil, fmt.Errorf("%s is required when %s=otlp", launcherOTLPLogsEndpointEnv, launcherLogsExporterEnv)
	}

	// If a workload identity token file is available, use a refreshable auth
	// transport that exchanges the projected SA token for platform credentials.
	if os.Getenv(workloadIdentityTokenFileEnv) != "" {
		tokenSource, err := newOTLPLogWorkloadAuthTokenSource(ctx)
		if err != nil {
			return nil, fmt.Errorf("configure workload identity auth for OTLP logs: %w", err)
		}
		return newRefreshableAuthLogExporter(ctx, endpointURL, tokenSource, otlpHTTPLogExporter)
	}

	options := []otlploghttp.Option{
		otlploghttp.WithEndpointURL(endpointURL),
		otlploghttp.WithHeaders(parseLauncherOTLPHeaders()),
	}

	timeout, timeoutSet, err := parseLauncherOTLPTimeout()
	if err != nil {
		return nil, err
	}
	if httpClient := launcherOTLPHTTPClient(timeout, timeoutSet); httpClient != nil {
		options = append(options, otlploghttp.WithHTTPClient(httpClient))
	}
	if timeoutSet {
		options = append(options, otlploghttp.WithTimeout(timeout))
	}
	if compression, ok, err := parseLauncherOTLPCompression(); err != nil {
		return nil, err
	} else if ok {
		options = append(options, otlploghttp.WithCompression(compression))
	}

	return otlploghttp.New(ctx, options...)
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

func launcherOTLPHTTPClient(timeout time.Duration, timeoutSet bool) *http.Client {
	endpoint, err := nmpclient.ResolvePlatformEndpointFromEnv()
	if err != nil || endpoint.Transport != nmpclient.TransportUDS {
		return nil
	}
	httpClient := endpoint.HTTPClient()
	if timeoutSet {
		httpClient.Timeout = timeout
	}
	return httpClient
}

func parseLauncherOTLPHeaders() map[string]string {
	raw := strings.TrimSpace(os.Getenv(launcherOTLPLogsHeadersEnv))
	if raw == "" {
		return nil
	}
	headers := map[string]string{}
	for _, item := range strings.Split(raw, ",") {
		key, value, ok := strings.Cut(strings.TrimSpace(item), "=")
		if !ok || key == "" {
			continue
		}
		if decoded, err := url.PathUnescape(value); err == nil {
			value = decoded
		}
		headers[key] = value
	}
	return headers
}

func parseLauncherOTLPTimeout() (time.Duration, bool, error) {
	raw := strings.TrimSpace(os.Getenv(launcherOTLPLogsTimeoutEnv))
	if raw == "" {
		return 0, false, nil
	}
	duration, err := time.ParseDuration(raw)
	if err == nil {
		return duration, true, nil
	}
	milliseconds, intErr := strconv.Atoi(raw)
	if intErr == nil {
		return time.Duration(milliseconds) * time.Millisecond, true, nil
	}
	return 0, false, fmt.Errorf("invalid %s value %q: %w", launcherOTLPLogsTimeoutEnv, raw, err)
}

func parseLauncherOTLPCompression() (otlploghttp.Compression, bool, error) {
	switch strings.ToLower(strings.TrimSpace(os.Getenv(launcherOTLPLogsCompressEnv))) {
	case "":
		return otlploghttp.NoCompression, false, nil
	case "none":
		return otlploghttp.NoCompression, true, nil
	case "gzip":
		return otlploghttp.GzipCompression, true, nil
	default:
		return otlploghttp.NoCompression, false, fmt.Errorf("unsupported %s value %q", launcherOTLPLogsCompressEnv, os.Getenv(launcherOTLPLogsCompressEnv))
	}
}

type noopLogExporter struct{}

func (noopLogExporter) Export(context.Context, []log.Record) error {
	return nil
}

func (noopLogExporter) Shutdown(context.Context) error {
	return nil
}

func (noopLogExporter) ForceFlush(context.Context) error {
	return nil
}
