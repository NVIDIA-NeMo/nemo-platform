// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

package telemetry

import (
	"context"
	"errors"
	"log"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/exporters/otlp/otlpmetric/otlpmetricgrpc"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
	"go.opentelemetry.io/otel/exporters/stdout/stdoutmetric"
	"go.opentelemetry.io/otel/exporters/stdout/stdouttrace"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/sdk/metric"
	"go.opentelemetry.io/otel/sdk/resource"
	"go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.34.0"
)

type Options struct {
	ServiceName          string
	TracingEnabled       bool
	MetricsEnabled       bool
	TracingStdoutEnabled bool
	MetricsStdoutEnabled bool
	TracingPeriod        time.Duration
	MetricsPeriod        time.Duration
	OTLPEndpoint         string
	OTLPInsecure         bool
}

type OtelManager struct {
	tracerProvider *trace.TracerProvider
	metricProvider *metric.MeterProvider
	shutdownFuncs  []func(context.Context) error
}

// NewOtelManager configures OpenTelemetry according to Options and returns a manager.
// After a successful return, you should call Shutdown for proper cleanup.
func NewOtelManager(ctx context.Context, opt Options) (*OtelManager, error) {
	// Set default period to 60 seconds if not set
	if opt.TracingPeriod == 0 {
		opt.TracingPeriod = 60 * time.Second
	}
	if opt.MetricsPeriod == 0 {
		opt.MetricsPeriod = 60 * time.Second
	}

	res, err := getResource(ctx, opt.ServiceName)
	if err != nil {
		return nil, err
	}

	// Set global propagator
	prop := propagation.NewCompositeTextMapPropagator(propagation.TraceContext{}, propagation.Baggage{})
	otel.SetTextMapPropagator(prop)

	otelManager := &OtelManager{shutdownFuncs: nil}

	// Set-up tracing
	if opt.TracingEnabled {
		traceOpts := []otlptracegrpc.Option{}
		if opt.OTLPEndpoint != "" {
			traceOpts = append(traceOpts, otlptracegrpc.WithEndpoint(opt.OTLPEndpoint))
		}
		if opt.OTLPInsecure {
			traceOpts = append(traceOpts, otlptracegrpc.WithInsecure())
		}
		extTraceExporter, err := otlptracegrpc.New(ctx, traceOpts...)
		if err != nil {
			return nil, otelManager.handleErr(ctx, err)
		}
		tracerProvider, err := otelManager.newTraceProvider(res, opt, extTraceExporter)
		if err != nil {
			return nil, otelManager.handleErr(ctx, err)
		}
		otelManager.tracerProvider = tracerProvider
		otelManager.shutdownFuncs = append(otelManager.shutdownFuncs, tracerProvider.Shutdown)
		otel.SetTracerProvider(tracerProvider)
	}

	// Set-up metrics
	if opt.MetricsEnabled {
		metricOpts := []otlpmetricgrpc.Option{}
		if opt.OTLPEndpoint != "" {
			metricOpts = append(metricOpts, otlpmetricgrpc.WithEndpoint(opt.OTLPEndpoint))
		}
		if opt.OTLPInsecure {
			metricOpts = append(metricOpts, otlpmetricgrpc.WithInsecure())
		}
		extMetricsExporter, err := otlpmetricgrpc.New(ctx, metricOpts...)
		if err != nil {
			return nil, otelManager.handleErr(ctx, err)
		}
		meterProvider, err := otelManager.newMeterProvider(res, opt, extMetricsExporter)
		if err != nil {
			return nil, otelManager.handleErr(ctx, err)
		}
		otelManager.metricProvider = meterProvider
		otelManager.shutdownFuncs = append(otelManager.shutdownFuncs, meterProvider.Shutdown)
		otel.SetMeterProvider(meterProvider)
	}

	return otelManager, nil
}

// Shutdown runs registered shutdown funcs
func (om *OtelManager) Shutdown(ctx context.Context) error {
	var err error
	for _, fn := range om.shutdownFuncs {
		err = errors.Join(err, fn(ctx))
	}
	om.shutdownFuncs = nil
	return err
}

func (om *OtelManager) handleErr(ctx context.Context, inErr error) error {
	return errors.Join(inErr, om.Shutdown(ctx))
}

// getResource - initialize process attributes
func getResource(ctx context.Context, serviceName string) (*resource.Resource, error) {
	res, err := resource.New(ctx,
		resource.WithFromEnv(),      // Discover and provide attributes from OTEL_RESOURCE_ATTRIBUTES and OTEL_SERVICE_NAME environment variables.
		resource.WithTelemetrySDK(), // Discover and provide information about the OpenTelemetry SDK used.
		resource.WithContainer(),    // Discover and provide container information.
		resource.WithHost(),         // Discover and provide host information.
		resource.WithSchemaURL(string(semconv.SchemaURL)),
	)
	if errors.Is(err, resource.ErrPartialResource) || errors.Is(err, resource.ErrSchemaURLConflict) {
		log.Printf("warning: error initializing resource: %v", err)
	} else if err != nil {
		return nil, err
	}
	// Prefer the provided service name if set
	if serviceName != "" {
		withSvc, svcErr := resource.Merge(res, resource.NewSchemaless(
			semconv.ServiceName(serviceName),
		))
		if svcErr == nil {
			res = withSvc
		} else {
			log.Printf("warning: failed to set service name resource attribute: %v", svcErr)
		}
	}
	return res, nil
}

func (om *OtelManager) newTraceProvider(res *resource.Resource, o Options, externalExp trace.SpanExporter) (*trace.TracerProvider, error) {
	tracingFrequency := o.TracingPeriod
	traceOptions := []trace.TracerProviderOption{
		trace.WithBatcher(externalExp, trace.WithBatchTimeout(tracingFrequency)),
		trace.WithResource(res),
	}
	if o.TracingStdoutEnabled {
		stdoutExp, err := stdouttrace.New(stdouttrace.WithPrettyPrint())
		if err != nil {
			return nil, err
		}
		traceOptions = append(traceOptions, trace.WithBatcher(stdoutExp, trace.WithBatchTimeout(tracingFrequency)))
	}
	return trace.NewTracerProvider(traceOptions...), nil
}

func (om *OtelManager) newMeterProvider(res *resource.Resource, o Options, externalExp metric.Exporter) (*metric.MeterProvider, error) {
	metricsFrequency := o.MetricsPeriod
	metricOptions := []metric.Option{
		metric.WithReader(metric.NewPeriodicReader(externalExp, metric.WithInterval(metricsFrequency))),
		metric.WithResource(res),
	}
	if o.MetricsStdoutEnabled {
		stdoutMetricExporter, err := stdoutmetric.New()
		if err != nil {
			return nil, err
		}
		metricOptions = append(metricOptions, metric.WithReader(metric.NewPeriodicReader(stdoutMetricExporter, metric.WithInterval(metricsFrequency))))
	}
	return metric.NewMeterProvider(metricOptions...), nil
}
