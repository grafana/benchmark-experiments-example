package demo

import (
	"context"
	"fmt"
	"io"

	"github.com/wei-chincall/grafana-oss-talks/internal/bench"
	"github.com/wei-chincall/grafana-oss-talks/internal/o11y"
)

func Write(w io.Writer) error {
	backend := o11y.FixtureBackend{}
	if err := intro(w); err != nil {
		return err
	}
	if err := metrics(w, backend); err != nil {
		return err
	}
	if err := logsAndTrace(w, backend); err != nil {
		return err
	}
	return dashboardAndScores(w, backend)
}

func intro(w io.Writer) error {
	_, err := fmt.Fprintln(w, "WatcherBench demo: debugging the dashboard debugger")
	if err != nil {
		return err
	}
	if _, err = fmt.Fprintln(w, "Scenario: checkout latency alert, wrong dashboard query, live benchmark framing"); err != nil {
		return err
	}
	_, err = fmt.Fprintln(w)
	return err
}

func metrics(w io.Writer, backend o11y.Backend) error {
	wrong := `rate(http_request_duration_seconds_sum[5m]) / rate(http_request_duration_seconds_count[5m])`
	right := `histogram_quantile(0.95, sum by (le,route)(rate(http_request_duration_seconds_bucket[5m])))`
	if err := printMetric(w, backend, "valid-but-wrong query", wrong); err != nil {
		return err
	}
	return printMetric(w, backend, "verified p95 query", right)
}

func printMetric(w io.Writer, backend o11y.Backend, label string, query string) error {
	out, err := backend.QueryMetrics(context.Background(), o11y.MetricQueryInput{Query: query})
	if err != nil {
		return err
	}
	_, err = fmt.Fprintf(w, "tool=fixture_query_prometheus label=%q value=%.2f %s warning=%q\n",
		label, out.Points[0].Value, out.Points[0].Unit, out.Warning)
	return err
}

func logsAndTrace(w io.Writer, backend o11y.Backend) error {
	logs, err := backend.QueryLogs(context.Background(), o11y.LogQueryInput{Query: `{service="checkout-api"} |= "failed"`})
	if err != nil {
		return err
	}
	trace, err := backend.FindTrace(context.Background(), o11y.TraceSearchInput{Service: "checkout-api"})
	if err != nil {
		return err
	}
	_, err = fmt.Fprintf(w, "tool=fixture_query_loki first_log=%q\n", logs.Lines[0].Line)
	if err != nil {
		return err
	}
	_, err = fmt.Fprintf(w, "tool=fixture_find_trace root=%q latency=%q\n", trace.Root, trace.Latency)
	return err
}

func dashboardAndScores(w io.Writer, backend o11y.Backend) error {
	patch, err := backend.PatchDashboard(context.Background(), demoPatch())
	if err != nil {
		return err
	}
	if _, err = fmt.Fprintf(w, "tool=fixture_patch_dashboard dry_run=true diff=%q\n\n", patch.Diff); err != nil {
		return err
	}
	return bench.WriteTable(w, bench.Summaries(sampleTrials()))
}

func demoPatch() o11y.DashboardPatchInput {
	return o11y.DashboardPatchInput{
		UID:     "checkout-overview",
		PanelID: 7,
		DryRun:  true,
		Query:   `histogram_quantile(0.95, sum by (le,route)(rate(http_request_duration_seconds_bucket[5m])))`,
	}
}

func sampleTrials() []bench.Trial {
	return []bench.Trial{
		{Agent: "consistent-agent", Task: "promql-p95", Attempt: 1, Score: 1, Passed: true},
		{Agent: "consistent-agent", Task: "promql-p95", Attempt: 2, Score: 1, Passed: true},
		{Agent: "consistent-agent", Task: "promql-p95", Attempt: 3, Score: 1, Passed: true},
		{Agent: "lucky-agent", Task: "promql-p95", Attempt: 1, Score: 1, Passed: true},
		{Agent: "lucky-agent", Task: "promql-p95", Attempt: 2, Score: 0, Passed: false},
		{Agent: "lucky-agent", Task: "promql-p95", Attempt: 3, Score: 0, Passed: false},
	}
}
