package o11y

import (
	"context"
	"strings"
	"testing"
)

func TestFixtureFlagsMeanLatencyAsWrongP95Evidence(t *testing.T) {
	backend := FixtureBackend{}
	out, err := backend.QueryMetrics(context.Background(), MetricQueryInput{
		Query: `rate(http_request_duration_seconds_sum[5m]) / rate(http_request_duration_seconds_count[5m])`,
	})
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(out.Warning, "wrong statistic") {
		t.Fatalf("expected warning, got %q", out.Warning)
	}
}

func TestValidateQueryRejectsTokenShape(t *testing.T) {
	if err := ValidateQuery(`{service="api"} |= "sk-test"`); err == nil {
		t.Fatal("expected token-like query to be rejected")
	}
}
