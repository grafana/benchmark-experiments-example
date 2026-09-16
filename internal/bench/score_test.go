package bench

import (
	"strings"
	"testing"
)

func TestSummariesSeparatePassAt3FromPassPow3(t *testing.T) {
	trials := []Trial{
		{Agent: "consistent", Task: "a", Attempt: 1, Score: 1, Passed: true},
		{Agent: "consistent", Task: "a", Attempt: 2, Score: 1, Passed: true},
		{Agent: "consistent", Task: "a", Attempt: 3, Score: 1, Passed: true},
		{Agent: "lucky", Task: "a", Attempt: 1, Score: 1, Passed: true},
		{Agent: "lucky", Task: "a", Attempt: 2, Score: 0, Passed: false},
		{Agent: "lucky", Task: "a", Attempt: 3, Score: 0, Passed: false},
	}
	summaries := Summaries(trials)
	if summaries[0].Agent != "consistent" {
		t.Fatalf("expected consistent first, got %s", summaries[0].Agent)
	}
	if summaries[1].PassAt3 != 1 {
		t.Fatalf("expected lucky Pass@3 to be 1, got %f", summaries[1].PassAt3)
	}
	if summaries[1].PassPow3 >= summaries[0].PassPow3 {
		t.Fatalf("expected consistency gap")
	}
}

func TestLoadTrialsRejectsInvalidScore(t *testing.T) {
	_, err := LoadTrials(strings.NewReader(`[{"agent":"a","task":"t","attempt":1,"score":1.1}]`))
	if err == nil {
		t.Fatal("expected error")
	}
}
