// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

package config

import (
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"maps"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	sigyaml "sigs.k8s.io/yaml"
)

const DEFAULT_REFUSAL_TEXT = "I'm sorry, I can't respond to that." // consisent with Guardrails MS.

type Config struct {
	GRPC       GRPC       `json:"grpc"`
	ExtProc    ExtProc    `json:"extproc"`
	Guardrails Guardrails `json:"guardrails"`
	Telemetry  Telemetry  `json:"telemetry"`
}

type GRPC struct {
	Address string    `json:"address"` // e.g. ":8080"
	TLS     TLSConfig `json:"tls"`
}

type TLSConfig struct {
	Enabled  bool   `json:"enabled"`
	CertFile string `json:"cert_file"`
	KeyFile  string `json:"key_file"`
}

type ExtProc struct {
	EventsPerCheck int `json:"events_per_check"`
}

type GuardrailsModelConfig struct {
	RefusalText string   `json:"refusal_text"`
	ConfigIDs   []string `json:"config_ids"`
}

// GetGuardrailsConfigIDs returns the guardrails config IDs for the given model.
// If none are configured, then return the default.
func (m GuardrailsModelConfig) GetGuardrailsConfigIDs() []string {
	if len(m.ConfigIDs) == 0 {
		// Explicitly zerio out the config_ids so that it gets serialized as `{}`
		// Guardrails MS will use DEFAULT_CONFIG_ID
		return nil
	}
	return m.ConfigIDs
}

type Guardrails struct {
	BaseURL            string                           `json:"base_url"`
	Timeout            time.Duration                    `json:"timeout"` // accepts strings like "3s"
	DefaultRefusalText string                           `json:"default_refusal_text"`
	Models             map[string]GuardrailsModelConfig `json:"models"`
}

// Telemetry holds OpenTelemetry exporter configuration.
type Telemetry struct {
	// ServiceName is used as OTEL service.name resource attribute.
	ServiceName string `json:"service_name"`
	// OTLPEndpoint is the host:port for the OTLP gRPC exporter (no scheme).
	OTLPEndpoint string `json:"otlp_endpoint"`
	// OTLPInsecure configures the exporter to use plaintext instead of TLS.
	OTLPInsecure bool `json:"otlp_insecure"`
	// Enabled disables Telemetry initialization when true.
	Enabled bool `json:"enabled"`
	// TracingEnabled controls whether tracing is enabled based on OTEL_TRACES_EXPORTER.
	TracingEnabled bool `json:"tracing_enabled"`
	// MetricsEnabled controls whether metrics are enabled based on OTEL_METRICS_EXPORTER.
	MetricsEnabled bool `json:"metrics_enabled"`
	// TracingStdoutEnabled enables stdout exporter for traces
	TracingStdoutEnabled bool `json:"tracing_stdout_enabled"`
	// MetricsStdoutEnabled enables stdout exporter for metrics
	MetricsStdoutEnabled bool `json:"metrics_stdout_enabled"`
}

func Load(path string) (Config, error) {
	// 1) Start with defaults
	cfg := defaults()

	// 2) Overlay file (if provided and exists)
	if path != "" {
		if fi, err := os.Stat(path); err == nil && !fi.IsDir() {
			if err := loadFile(path, &cfg); err != nil {
				return Config{}, fmt.Errorf("load file: %w", err)
			}
		}
	}

	// 3) Overlay environment variables
	if err := loadEnv("GR", &cfg); err != nil {
		return Config{}, fmt.Errorf("load env: %w", err)
	}

	// 4) Validate
	if err := cfg.Validate(); err != nil {
		return Config{}, err
	}
	return cfg, nil
}

func defaults() Config {
	return Config{
		GRPC: GRPC{
			Address: ":8443",
			TLS: TLSConfig{
				Enabled:  false,
				CertFile: "ssl_creds/server.crt", // baked into the docker image
				KeyFile:  "ssl_creds/server.key", // baked into the docker image
			},
		},
		ExtProc: ExtProc{
			// Default to 200 chat completion chunks per check. Analogous to guardrails framework's chunk_size.
			// https://github.com/NVIDIA-NeMo/Guardrails/blob/ba4c321ed058507831e81804604c4162103dc190/nemoguardrails/rails/llm/config.py#L440
			EventsPerCheck: 200,
		},
		Guardrails: Guardrails{
			BaseURL:            "http://guardrails:7331",
			Timeout:            8 * time.Second,
			Models:             make(map[string]GuardrailsModelConfig),
			DefaultRefusalText: DEFAULT_REFUSAL_TEXT,
		},
		Telemetry: Telemetry{
			ServiceName:          "guardrails-ext-proc-service",
			OTLPEndpoint:         "localhost:4317",
			OTLPInsecure:         true,
			Enabled:              true,
			TracingEnabled:       true,
			MetricsEnabled:       true,
			TracingStdoutEnabled: false,
			MetricsStdoutEnabled: false,
		},
	}
}

func loadFile(path string, cfg *Config) error {
	log.Printf("Loading config file from %s", path)
	// For stdlib-only simplicity, use JSON for now.
	// If the file ends with .yaml/.yml, you can pre-convert it to JSON externally.
	switch strings.ToLower(filepath.Ext(path)) {
	case ".yaml", ".yml":
		b, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		var fileCfg Config
		jb, err := sigyaml.YAMLToJSONStrict(b)
		if err != nil {
			return err
		}
		if err := json.Unmarshal(jb, &fileCfg); err != nil {
			return err
		}
		merge(cfg, fileCfg)
	case ".json":
		b, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		// Unmarshal into a temporary and merge to preserve zero-value semantics.
		var fileCfg Config
		if err := json.Unmarshal(b, &fileCfg); err != nil {
			return fmt.Errorf("failed to unmarshal json: %w", err)
		}
		merge(cfg, fileCfg)
	default:
		return fmt.Errorf("unsupported file extension: %s (use .json for stdlib-only)", path)
	}
	return nil
}

// merge overlays non-zero values from src into dst.
// For scalar numeric/bool/string, zero means “ignore”. For Duration, zero is ignored.
// For nested structs, it merges recursively.
func merge(dst *Config, src Config) {
	// GRPC
	if src.GRPC.Address != "" {
		dst.GRPC.Address = src.GRPC.Address
	}
	// TLS
	if src.GRPC.TLS.Enabled {
		dst.GRPC.TLS.Enabled = true
	}
	if src.GRPC.TLS.CertFile != "" {
		dst.GRPC.TLS.CertFile = src.GRPC.TLS.CertFile
	}
	if src.GRPC.TLS.KeyFile != "" {
		dst.GRPC.TLS.KeyFile = src.GRPC.TLS.KeyFile
	}

	// ExtProc
	if src.ExtProc.EventsPerCheck != 0 {
		dst.ExtProc.EventsPerCheck = src.ExtProc.EventsPerCheck
	}

	// Guardrails
	if src.Guardrails.BaseURL != "" {
		dst.Guardrails.BaseURL = src.Guardrails.BaseURL
	}
	if src.Guardrails.Timeout != 0 {
		dst.Guardrails.Timeout = src.Guardrails.Timeout
	}
	if len(src.Guardrails.Models) != 0 {
		maps.Copy(dst.Guardrails.Models, src.Guardrails.Models)
	}

	// Telemetry
	if src.Telemetry.ServiceName != "" {
		dst.Telemetry.ServiceName = src.Telemetry.ServiceName
	}
	if src.Telemetry.OTLPEndpoint != "" {
		dst.Telemetry.OTLPEndpoint = src.Telemetry.OTLPEndpoint
	}
	if src.Telemetry.OTLPInsecure {
		dst.Telemetry.OTLPInsecure = true
	}
	if src.Telemetry.Enabled {
		dst.Telemetry.Enabled = true
	}
	if src.Telemetry.TracingEnabled {
		dst.Telemetry.TracingEnabled = true
	}
	if src.Telemetry.MetricsEnabled {
		dst.Telemetry.MetricsEnabled = true
	}
	if src.Telemetry.TracingStdoutEnabled {
		dst.Telemetry.TracingStdoutEnabled = true
	}
	if src.Telemetry.MetricsStdoutEnabled {
		dst.Telemetry.MetricsStdoutEnabled = true
	}
}

func loadEnv(prefix string, cfg *Config) error {
	// Expect env vars like:
	//   GR_GRPC__ADDRESS=":8443"
	//   GR_GRPC__TLS__ENABLED=true
	//   GR_GRPC__TLS__CERT_FILE="/path/tls.crt"
	//   GR_GRPC__TLS__KEY_FILE="/path/tls.key"
	//   GR_EXTPROC__EVENTS_PER_CHECK=1
	//   GR_EXTPROC__RESPONSE_STREAM__FULL_DUPLEX=true
	//   GR_GUARDRAILS__BASE_URL="https://guardrails.svc"
	//   GR_GUARDRAILS__TIMEOUT="5s"

	// Collect and apply known keys. This avoids reflection and keeps it fast and explicit.
	get := func(k string) (string, bool) {
		return os.LookupEnv(prefix + "_" + k)
	}

	// GRPC
	if v, ok := get("GRPC__ADDRESS"); ok && v != "" {
		cfg.GRPC.Address = v
	}
	if v, ok := get("GRPC__TLS__ENABLED"); ok && v != "" {
		if b, err := parseBool(v); err == nil {
			cfg.GRPC.TLS.Enabled = b
		} else {
			return fmt.Errorf("cannot parse GRPC__TLS__ENABLED: %w", err)
		}
	}
	if v, ok := get("GRPC__TLS__CERT_FILE"); ok && v != "" {
		cfg.GRPC.TLS.CertFile = v
	}
	if v, ok := get("GRPC__TLS__KEY_FILE"); ok && v != "" {
		cfg.GRPC.TLS.KeyFile = v
	}

	// ExtProc
	if v, ok := get("EXTPROC__EVENTS_PER_CHECK"); ok && v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			cfg.ExtProc.EventsPerCheck = n
		} else {
			return fmt.Errorf("cannot parse EXTPROC__EVENTS_PER_CHECK: %w", err)
		}
	}

	// Guardrails
	if v, ok := get("GUARDRAILS__BASE_URL"); ok && v != "" {
		cfg.Guardrails.BaseURL = v
	}
	if v, ok := get("GUARDRAILS__TIMEOUT"); ok && v != "" {
		d, err := time.ParseDuration(v)
		if err != nil {
			return fmt.Errorf("cannot parse GUARDRAILS__TIMEOUT: %w", err)
		}
		cfg.Guardrails.Timeout = d
	}
	if v, ok := get("GUARDRAILS__DEFAULT_REFUSAL_TEXT"); ok && v != "" {
		cfg.Guardrails.DefaultRefusalText = v
	}

	// Otel
	if v, ok := os.LookupEnv("OTEL_EXPORTER_OTLP_ENDPOINT"); ok && v != "" {
		endpoint := strings.ToLower(strings.TrimSpace(v))
		// Normalize any scheme prefix to satisfy WithEndpoint expectations
		if strings.HasPrefix(endpoint, "http://") {
			endpoint = strings.TrimPrefix(endpoint, "http://")
		} else if strings.HasPrefix(endpoint, "https://") {
			endpoint = strings.TrimPrefix(endpoint, "https://")
		}

		cfg.Telemetry.OTLPEndpoint = endpoint
	}
	if v, ok := os.LookupEnv("OTEL_EXPORTER_OTLP_INSECURE"); ok && v != "" {
		if b, err := parseBool(v); err == nil {
			cfg.Telemetry.OTLPInsecure = b
		} else {
			log.Printf("warning: could not parse OTEL_EXPORTER_OTLP_INSECURE=%q; defaulting to insecure=true", v)
			cfg.Telemetry.OTLPInsecure = true
		}
	}
	if v, ok := os.LookupEnv("OTEL_SERVICE_NAME"); ok && v != "" {
		cfg.Telemetry.ServiceName = v
	}

	if v, ok := os.LookupEnv("OTEL_SDK_DISABLED"); ok && v != "" {
		if b, err := parseBool(v); err == nil {
			// Enabled is the inverse of OTEL_SDK_DISABLED
			cfg.Telemetry.Enabled = !b
		} else {
			log.Printf("warning: could not parse OTEL_SDK_DISABLED=%q; leaving telemetry enabled=%v", v, cfg.Telemetry.Enabled)
		}
	}

	// Determine traces and metrics enable/disable from standard OTEL env vars.
	// Per spec exporter enums (https://opentelemetry.io/docs/specs/otel/configuration/sdk-environment-variables/#exporter-selection):
	//  - Traces can be: otlp, zipkin, console, logging, none
	//  - Metrics can be: otlp, prometheus, console, logging, none
	// If a comma-separated list is provided, use the default values.

	if v, ok := os.LookupEnv("OTEL_TRACES_EXPORTER"); ok && v != "" {
		val := strings.ToLower(strings.TrimSpace(v))

		switch val {
		case "console", "logging":
			cfg.Telemetry.TracingEnabled = true
			cfg.Telemetry.TracingStdoutEnabled = true
		case "none":
			cfg.Telemetry.TracingEnabled = false
		case "otlp", "zipkin":
			cfg.Telemetry.TracingEnabled = true
		default:
			cfg.Telemetry.TracingEnabled = true
		}
	}
	if v, ok := os.LookupEnv("OTEL_METRICS_EXPORTER"); ok && v != "" {
		val := strings.ToLower(strings.TrimSpace(v))

		switch val {
		case "console", "logging":
			cfg.Telemetry.MetricsEnabled = true
			cfg.Telemetry.MetricsStdoutEnabled = true
		case "none":
			cfg.Telemetry.MetricsEnabled = false
		case "otlp", "prometheus":
			cfg.Telemetry.MetricsEnabled = true
		default:
			cfg.Telemetry.MetricsEnabled = true
		}
	}
	return nil
}

func parseBool(s string) (bool, error) {
	switch strings.ToLower(strings.TrimSpace(s)) {
	case "1", "true":
		return true, nil
	case "0", "false":
		return false, nil
	default:
		return false, fmt.Errorf("invalid bool %q", s)
	}
}

func (c Config) Validate() error {
	// gRPC
	if strings.TrimSpace(c.GRPC.Address) == "" {
		return errors.New("grpc.address required")
	}
	if c.GRPC.TLS.Enabled {
		if c.GRPC.TLS.CertFile == "" || c.GRPC.TLS.KeyFile == "" {
			return errors.New("grpc.tls enabled but cert_file/key_file missing")
		}
		if _, err := os.Stat(c.GRPC.TLS.CertFile); err != nil {
			return fmt.Errorf("grpc.tls.cert_file: %w", err)
		}
		if _, err := os.Stat(c.GRPC.TLS.KeyFile); err != nil {
			return fmt.Errorf("grpc.tls.key_file: %w", err)
		}
	}

	// ExtProc
	if c.ExtProc.EventsPerCheck < 0 {
		return errors.New("extproc.events_per_check must be >= 0")
	}

	// Guardrails
	if strings.TrimSpace(c.Guardrails.BaseURL) == "" {
		return errors.New("guardrails.base_url required")
	}
	if c.Guardrails.Timeout <= 0 {
		return errors.New("guardrails.timeout must be > 0")
	}
	if c.Guardrails.Models == nil {
		return errors.New("guardrails.models cannot be nil")
	}
	if c.Guardrails.DefaultRefusalText == "" {
		return errors.New("guardrails.default_refusal_text cannot be empty")
	}
	return nil
}
