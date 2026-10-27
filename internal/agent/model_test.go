package agent

import "testing"

func TestNormalizeModelStripsProviderPrefix(t *testing.T) {
	got := NormalizeModel("anthropic/claude-sonnet-4-6")
	if got != "claude-sonnet-4-6" {
		t.Fatalf("unexpected model %q", got)
	}
}
