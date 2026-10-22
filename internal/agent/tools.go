package agent

import (
	"context"
	"encoding/json"

	aisdk "github.com/grafana/ai-sdk"
	"github.com/wei-chincall/grafana-oss-talks/internal/o11y"
)

func Tools(backend o11y.Backend) (aisdk.ToolSet, error) {
	metrics, err := metricsTool(backend)
	if err != nil {
		return nil, err
	}
	logs, err := logsTool(backend)
	if err != nil {
		return nil, err
	}
	trace, err := traceTool(backend)
	if err != nil {
		return nil, err
	}
	patch, err := patchTool(backend)
	if err != nil {
		return nil, err
	}
	return aisdk.ToolSet{
		"fixture_query_prometheus": metrics,
		"fixture_query_loki":       logs,
		"fixture_find_trace":       trace,
		"fixture_patch_dashboard":  patch,
	}, nil
}

func metricsTool(backend o11y.Backend) (aisdk.Tool, error) {
	return aisdk.TypedTool(aisdk.TypedToolDef[o11y.MetricQueryInput, o11y.MetricQueryOutput]{
		Name:        "fixture_query_prometheus",
		Description: "Run a PromQL query and return matching metric series.",
		Execute: func(ctx context.Context, input o11y.MetricQueryInput, _ aisdk.ToolExecutionOptions) (o11y.MetricQueryOutput, error) {
			return backend.QueryMetrics(ctx, input)
		},
		ValidateInput: func(input o11y.MetricQueryInput) error {
			return o11y.ValidateQuery(input.Query)
		},
	})
}

func logsTool(backend o11y.Backend) (aisdk.Tool, error) {
	return aisdk.TypedTool(aisdk.TypedToolDef[o11y.LogQueryInput, o11y.LogQueryOutput]{
		Name:        "fixture_query_loki",
		Description: "Run a LogQL query and return relevant log lines.",
		Execute: func(ctx context.Context, input o11y.LogQueryInput, _ aisdk.ToolExecutionOptions) (o11y.LogQueryOutput, error) {
			return backend.QueryLogs(ctx, input)
		},
		ValidateInput: func(input o11y.LogQueryInput) error {
			return o11y.ValidateQuery(input.Query)
		},
	})
}

func traceTool(backend o11y.Backend) (aisdk.Tool, error) {
	return aisdk.TypedTool(aisdk.TypedToolDef[o11y.TraceSearchInput, o11y.TraceSummary]{
		Name:        "fixture_find_trace",
		Description: "Find a representative Tempo trace for a service and error hint.",
		Execute: func(ctx context.Context, input o11y.TraceSearchInput, _ aisdk.ToolExecutionOptions) (o11y.TraceSummary, error) {
			return backend.FindTrace(ctx, input)
		},
	})
}

func patchTool(backend o11y.Backend) (aisdk.Tool, error) {
	tool, err := aisdk.TypedTool(aisdk.TypedToolDef[o11y.DashboardPatchInput, o11y.DashboardPatchOutput]{
		Name:        "fixture_patch_dashboard",
		Description: "Patch a Grafana dashboard panel query; supports dry-run diffing.",
		Execute: func(ctx context.Context, input o11y.DashboardPatchInput, _ aisdk.ToolExecutionOptions) (o11y.DashboardPatchOutput, error) {
			return backend.PatchDashboard(ctx, input)
		},
		ValidateInput: o11y.ValidateDashboardPatch,
	})
	if err != nil {
		return aisdk.Tool{}, err
	}
	tool.NeedsApproval = aisdk.ApprovalIf(patchNeedsApproval)
	return tool, nil
}

func patchNeedsApproval(input json.RawMessage, _ aisdk.ToolExecutionOptions) (bool, error) {
	var patch o11y.DashboardPatchInput
	if err := json.Unmarshal(input, &patch); err != nil {
		return false, err
	}
	return !patch.DryRun, nil
}
