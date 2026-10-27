package o11y

type MetricQueryInput struct {
	Query  string `json:"query"`
	Window string `json:"window,omitempty"`
}

type MetricPoint struct {
	Series string  `json:"series"`
	Value  float64 `json:"value"`
	Unit   string  `json:"unit"`
	At     string  `json:"at"`
}

type MetricQueryOutput struct {
	Query   string        `json:"query"`
	Points  []MetricPoint `json:"points"`
	Warning string        `json:"warning,omitempty"`
}

type LogQueryInput struct {
	Query string `json:"query"`
	Limit int    `json:"limit,omitempty"`
}

type LogLine struct {
	Time    string `json:"time"`
	Service string `json:"service"`
	Line    string `json:"line"`
}

type LogQueryOutput struct {
	Query string    `json:"query"`
	Lines []LogLine `json:"lines"`
}

type TraceSearchInput struct {
	Service string `json:"service"`
	Error   string `json:"error,omitempty"`
}

type TraceSummary struct {
	TraceID string `json:"traceId"`
	Service string `json:"service"`
	Root    string `json:"root"`
	Latency string `json:"latency"`
}

type DashboardPatchInput struct {
	UID     string `json:"uid"`
	PanelID int    `json:"panelId"`
	Query   string `json:"query"`
	DryRun  bool   `json:"dryRun"`
}

type DashboardPatchOutput struct {
	UID     string `json:"uid"`
	PanelID int    `json:"panelId"`
	Applied bool   `json:"applied"`
	Diff    string `json:"diff"`
}
