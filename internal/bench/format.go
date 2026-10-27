package bench

import (
	"fmt"
	"io"
	"text/tabwriter"
)

func WriteTable(w io.Writer, summaries []Summary) error {
	tw := tabwriter.NewWriter(w, 0, 0, 2, ' ', 0)
	if _, err := fmt.Fprintln(tw, "AGENT\tTASKS\tTRIALS\tPASS^3\tPASS@3"); err != nil {
		return err
	}
	for _, summary := range summaries {
		if err := writeSummary(tw, summary); err != nil {
			return err
		}
	}
	return tw.Flush()
}

func writeSummary(w io.Writer, summary Summary) error {
	_, err := fmt.Fprintf(
		w,
		"%s\t%d\t%d\t%.1f%%\t%.1f%%\n",
		summary.Agent,
		summary.Tasks,
		summary.Trials,
		summary.PassPow3*100,
		summary.PassAt3*100,
	)
	return err
}
