package o11y

import "context"

type Backend interface {
	QueryMetrics(context.Context, MetricQueryInput) (MetricQueryOutput, error)
	QueryLogs(context.Context, LogQueryInput) (LogQueryOutput, error)
	FindTrace(context.Context, TraceSearchInput) (TraceSummary, error)
	PatchDashboard(context.Context, DashboardPatchInput) (DashboardPatchOutput, error)
}
