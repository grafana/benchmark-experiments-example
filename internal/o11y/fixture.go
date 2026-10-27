package o11y

import (
	"context"
	"strings"
)

type FixtureBackend struct{}

func (FixtureBackend) QueryMetrics(_ context.Context, input MetricQueryInput) (MetricQueryOutput, error) {
	if err := ValidateQuery(input.Query); err != nil {
		return MetricQueryOutput{}, err
	}
	if strings.Contains(input.Query, "histogram_quantile") {
		return p95Latency(input.Query), nil
	}
	if strings.Contains(input.Query, "_sum") && strings.Contains(input.Query, "_count") {
		return meanLatency(input.Query), nil
	}
	return checkoutOverview(input.Query), nil
}

func (FixtureBackend) QueryLogs(_ context.Context, input LogQueryInput) (LogQueryOutput, error) {
	if err := ValidateQuery(input.Query); err != nil {
		return LogQueryOutput{}, err
	}
	limit := input.Limit
	if limit <= 0 || limit > len(logLines) {
		limit = len(logLines)
	}
	return LogQueryOutput{Query: input.Query, Lines: logLines[:limit]}, nil
}

func (FixtureBackend) FindTrace(_ context.Context, input TraceSearchInput) (TraceSummary, error) {
	service := strings.TrimSpace(input.Service)
	if service == "" {
		service = "checkout-api"
	}
	return TraceSummary{
		TraceID: "8f52d1a0b7f9c044",
		Service: service,
		Root:    "payment-gateway retries after HTTP 429",
		Latency: "2.31s p95, 640ms database span",
	}, nil
}

func (FixtureBackend) PatchDashboard(_ context.Context, input DashboardPatchInput) (DashboardPatchOutput, error) {
	if err := ValidateDashboardPatch(input); err != nil {
		return DashboardPatchOutput{}, err
	}
	return DashboardPatchOutput{
		UID:     input.UID,
		PanelID: input.PanelID,
		Applied: !input.DryRun,
		Diff:    "replace mean latency query with histogram_quantile p95 query",
	}, nil
}

func p95Latency(query string) MetricQueryOutput {
	return MetricQueryOutput{Query: query, Points: []MetricPoint{{
		Series: `service="checkout-api",route="/cart/checkout"`,
		Value:  2.31,
		Unit:   "seconds",
		At:     "2026-11-02T18:42:00Z",
	}}}
}

func meanLatency(query string) MetricQueryOutput {
	return MetricQueryOutput{Query: query, Warning: "valid PromQL, wrong statistic for p95 latency", Points: []MetricPoint{{
		Series: `service="checkout-api",route="/cart/checkout"`,
		Value:  0.41,
		Unit:   "seconds",
		At:     "2026-11-02T18:42:00Z",
	}}}
}

func checkoutOverview(query string) MetricQueryOutput {
	return MetricQueryOutput{Query: query, Points: []MetricPoint{{
		Series: `service="checkout-api",status="5xx"`,
		Value:  0.074,
		Unit:   "ratio",
		At:     "2026-11-02T18:42:00Z",
	}}}
}

var logLines = []LogLine{
	{Time: "2026-11-02T18:39:14Z", Service: "checkout-api", Line: "payment authorize retry=2 status=429"},
	{Time: "2026-11-02T18:40:02Z", Service: "checkout-api", Line: "cart checkout failed cause=payment-gateway"},
	{Time: "2026-11-02T18:41:55Z", Service: "payment-gateway", Line: "rate limit bucket exhausted tenant=demo"},
}
