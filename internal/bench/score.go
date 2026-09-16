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
		return summaries[i].PassPow3 > summaries[j].PassPow3
	})
	return summaries
}

func summarizeAgent(agent string, trials []Trial) Summary {
	tasks := map[string]bool{}
	scoreTotal := 0.0
	for _, trial := range trials {
		tasks[trial.Task] = tasks[trial.Task] || trial.Passed
		scoreTotal += trial.Score
	}
	return Summary{
		Agent:    agent,
		Tasks:    len(tasks),
		Trials:   len(trials),
		PassAt3:  passAt3(tasks),
		PassPow3: scoreTotal / float64(len(trials)),
	}
}

func passAt3(tasks map[string]bool) float64 {
	if len(tasks) == 0 {
		return 0
	}
	passed := 0
	for _, ok := range tasks {
		if ok {
			passed++
		}
	}
	return float64(passed) / float64(len(tasks))
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
