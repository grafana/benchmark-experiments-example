package bench

import (
	"encoding/json"
	"fmt"
	"io"
	"sort"
)

type Trial struct {
	Agent    string  `json:"agent"`
	Task     string  `json:"task"`
	Category string  `json:"category"`
	Attempt  int     `json:"attempt"`
	Score    float64 `json:"score"`
	Passed   bool    `json:"passed"`
}

type Summary struct {
	Agent    string
	Tasks    int
	Trials   int
	PassAt3  float64
	PassPow3 float64
}

func LoadTrials(r io.Reader) ([]Trial, error) {
	var trials []Trial
	if err := json.NewDecoder(r).Decode(&trials); err != nil {
		return nil, err
	}
	for index, trial := range trials {
		if err := validateTrial(trial); err != nil {
			return nil, fmt.Errorf("trial %d: %w", index, err)
		}
	}
	return trials, nil
}

func Summaries(trials []Trial) []Summary {
	byAgent := map[string][]Trial{}
	for _, trial := range trials {
		byAgent[trial.Agent] = append(byAgent[trial.Agent], trial)
	}
	summaries := make([]Summary, 0, len(byAgent))
	for agent, agentTrials := range byAgent {
		summaries = append(summaries, summarizeAgent(agent, agentTrials))
	}
	sort.Slice(summaries, func(i, j int) bool {
		a, b := summaries[i], summaries[j]
		if a.PassPow3 != b.PassPow3 {
			return a.PassPow3 > b.PassPow3
		}
		if a.PassAt3 != b.PassAt3 {
			return a.PassAt3 > b.PassAt3
		}
		return a.Agent < b.Agent
	})
	return summaries
}

// taskOutcome tracks one task's trials: Pass@k needs any pass, Pass^k needs all.
type taskOutcome struct {
	anyPassed bool
	allPassed bool
}

func summarizeAgent(agent string, trials []Trial) Summary {
	tasks := map[string]*taskOutcome{}
	for _, trial := range trials {
		outcome, ok := tasks[trial.Task]
		if !ok {
			outcome = &taskOutcome{allPassed: true}
			tasks[trial.Task] = outcome
		}
		outcome.anyPassed = outcome.anyPassed || trial.Passed
		outcome.allPassed = outcome.allPassed && trial.Passed
	}
	return Summary{
		Agent:    agent,
		Tasks:    len(tasks),
		Trials:   len(trials),
		PassAt3:  taskFraction(tasks, func(o *taskOutcome) bool { return o.anyPassed }),
		PassPow3: taskFraction(tasks, func(o *taskOutcome) bool { return o.allPassed }),
	}
}

// taskFraction is the share of tasks whose outcome meets the criterion.
func taskFraction(tasks map[string]*taskOutcome, met func(*taskOutcome) bool) float64 {
	if len(tasks) == 0 {
		return 0
	}
	count := 0
	for _, outcome := range tasks {
		if met(outcome) {
			count++
		}
	}
	return float64(count) / float64(len(tasks))
}

func validateTrial(trial Trial) error {
	if trial.Agent == "" || trial.Task == "" {
		return fmt.Errorf("agent and task are required")
	}
	if trial.Attempt <= 0 {
		return fmt.Errorf("attempt must be positive")
	}
	if trial.Score < 0 || trial.Score > 1 {
		return fmt.Errorf("score must be between 0 and 1")
	}
	return nil
}
