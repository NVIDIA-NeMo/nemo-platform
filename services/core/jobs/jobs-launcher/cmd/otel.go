// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

package cmd

import (
	"context"
	"errors"
	"log/slog"
	"os"

	"go.opentelemetry.io/contrib/bridges/otelslog"
	"go.opentelemetry.io/contrib/exporters/autoexport"
	"go.opentelemetry.io/otel/attribute"
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
	loggerProvider, err := newLoggerProvider(res)
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
func newLoggerProvider(res *resource.Resource) (*log.LoggerProvider, error) {
	logExporter, err := autoexport.NewLogExporter(
		context.Background(),
		// Default to a stdout log exporter if autoexport fails to configure one.
		autoexport.WithFallbackLogExporter(
			func(ctx context.Context) (log.Exporter, error) {
				return stdoutlog.New()
			},
		),
	)
	if err != nil {
		return nil, err
	}

	loggerProvider := log.NewLoggerProvider(
		log.WithProcessor(log.NewBatchProcessor(logExporter)),
		log.WithResource(res),
	)
	return loggerProvider, nil
}
