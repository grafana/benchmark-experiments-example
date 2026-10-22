package main

import (
	"bytes"
	"context"
	"strings"
	"testing"
	"time"
)

func TestMCPTokenPrefersExplicitEnvToken(t *testing.T) {
	t.Setenv("HOME", t.TempDir())
	t.Setenv("XDG_CONFIG_HOME", "")
	t.Setenv("MCP_ACCESS_TOKEN", " injected-token \n")
	var stderr bytes.Buffer
	tok, err := mcpToken(context.Background(), "https://mcp.example/mcp", 10*time.Minute, &stderr)
	if err != nil || tok != "injected-token" || stderr.Len() != 0 {
		t.Fatalf("mcpToken = %q, %v, stderr %q", tok, err, stderr.String())
	}
}

func TestMCPTokenWithoutLoginConnectsWithoutToken(t *testing.T) {
	t.Setenv("HOME", t.TempDir())
	t.Setenv("XDG_CONFIG_HOME", "")
	t.Setenv("MCP_ACCESS_TOKEN", "")
	var stderr bytes.Buffer
	tok, err := mcpToken(context.Background(), "https://mcp.example/mcp", 10*time.Minute, &stderr)
	if err != nil || tok != "" {
		t.Fatalf("mcpToken = %q, %v", tok, err)
	}
	if !strings.Contains(stderr.String(), "without a token") {
		t.Fatalf("expected a warning, got %q", stderr.String())
	}
}
