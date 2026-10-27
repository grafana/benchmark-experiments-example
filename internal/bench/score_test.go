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
	if summaries[0].PassPow3 != 1 || summaries[1].PassPow3 != 0 {
		t.Fatalf("expected Pass^3 1 and 0, got %f and %f", summaries[0].PassPow3, summaries[1].PassPow3)
	}
}

func TestPassPow3CountsTasksWhereEveryTrialPassed(t *testing.T) {
	trials := []Trial{
		{Agent: "a", Task: "steady", Attempt: 1, Score: 0.6, Passed: true},
		{Agent: "a", Task: "steady", Attempt: 2, Score: 0.6, Passed: true},
		{Agent: "a", Task: "flaky", Attempt: 1, Score: 1, Passed: true},
		{Agent: "a", Task: "flaky", Attempt: 2, Score: 1, Passed: false},
		{Agent: "a", Task: "never", Attempt: 1, Score: 0, Passed: false},
		{Agent: "a", Task: "never", Attempt: 2, Score: 0, Passed: false},
	}
	got := Summaries(trials)[0]
	// Scores don't matter: steady passes all trials despite low scores, and
	// flaky's high scores don't make up for its failed trial.
	if got.PassPow3 != 1.0/3 || got.PassAt3 != 2.0/3 {
		t.Fatalf("Pass^3 = %f, Pass@3 = %f; want 1/3 and 2/3", got.PassPow3, got.PassAt3)
	}
}

func TestSummariesOrderIsDeterministic(t *testing.T) {
	trials := []Trial{
		{Agent: "b", Task: "t", Attempt: 1, Score: 1, Passed: true},
		{Agent: "c", Task: "t", Attempt: 1, Score: 0, Passed: false},
		{Agent: "a", Task: "t", Attempt: 1, Score: 1, Passed: true},
	}
	for range 20 {
		summaries := Summaries(trials)
		if summaries[0].Agent != "a" || summaries[1].Agent != "b" || summaries[2].Agent != "c" {
			t.Fatalf("unexpected order %s, %s, %s", summaries[0].Agent, summaries[1].Agent, summaries[2].Agent)
		}
	}
}

func TestLoadTrialsRejectsInvalidScore(t *testing.T) {
	_, err := LoadTrials(strings.NewReader(`[{"agent":"a","task":"t","attempt":1,"score":1.1}]`))
	if err == nil {
		t.Fatal("expected error")
	}
}
