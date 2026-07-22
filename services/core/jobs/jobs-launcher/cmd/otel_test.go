// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

package cmd

import (
	"testing"
	"time"
)

func TestLauncherOTLPHTTPClientSetsUDSTimeout(t *testing.T) {
	t.Setenv("NMP_BASE_URL", "unix:///tmp/nemo-platform.sock")

	client := launcherOTLPHTTPClient(250*time.Millisecond, true)
	if client == nil {
		t.Fatal("expected UDS HTTP client")
	}
	if client.Timeout != 250*time.Millisecond {
		t.Fatalf("expected UDS HTTP client timeout 250ms, got %s", client.Timeout)
	}
}

func TestLauncherOTLPHTTPClientLeavesUDSTimeoutUnset(t *testing.T) {
	t.Setenv("NMP_BASE_URL", "unix:///tmp/nemo-platform.sock")

	client := launcherOTLPHTTPClient(250*time.Millisecond, false)
	if client == nil {
		t.Fatal("expected UDS HTTP client")
	}
	if client.Timeout != 0 {
		t.Fatalf("expected UDS HTTP client timeout to remain unset, got %s", client.Timeout)
	}
}

func TestLauncherOTLPHTTPClientSkipsTCP(t *testing.T) {
	t.Setenv("NMP_BASE_URL", "http://127.0.0.1:8080")

	if client := launcherOTLPHTTPClient(250*time.Millisecond, true); client != nil {
		t.Fatal("expected no custom HTTP client for TCP endpoint")
	}
}
