package main

import (
	"context"
	"flag"
	"fmt"
	"io"
	"os"
	"strings"
	"time"

	"github.com/wei-chincall/grafana-oss-talks/internal/agent"
	"github.com/wei-chincall/grafana-oss-talks/internal/bench"
	"github.com/wei-chincall/grafana-oss-talks/internal/demo"
	"github.com/wei-chincall/grafana-oss-talks/internal/o11y"
)

func main() {
	if err := run(os.Args[1:], os.Stdout, os.Stderr); err != nil {
		fmt.Fprintln(os.Stderr, "error:", err)
		os.Exit(1)
	}
}

func run(args []string, stdout io.Writer, stderr io.Writer) error {
	if len(args) == 0 {
		return usage(stderr)
	}
	switch args[0] {
	case "demo":
		return demo.Write(stdout)
	case "score":
		return score(args[1:], stdout, stderr)
	case "ask":
		return ask(args[1:], stdout, stderr)
	case "bench-agent":
		return benchAgent(args[1:], stdout, stderr)
	default:
		return usage(stderr)
	}
}

func usage(w io.Writer) error {
	_, err := fmt.Fprintln(w, "usage: watcherbench [demo|score|ask|bench-agent]")
	return err
}

func score(args []string, stdout io.Writer, stderr io.Writer) error {
	fs := flag.NewFlagSet("score", flag.ContinueOnError)
	fs.SetOutput(stderr)
	path := fs.String("file", "bench/sample-results.json", "trial JSON file")
	if err := fs.Parse(args); err != nil {
		return err
	}
	file, err := os.Open(*path)
	if err != nil {
		return err
	}
	defer file.Close()
	trials, err := bench.LoadTrials(file)
	if err != nil {
		return err
	}
	return bench.WriteTable(stdout, bench.Summaries(trials))
}

func ask(args []string, stdout io.Writer, stderr io.Writer) error {
	fs := flag.NewFlagSet("ask", flag.ContinueOnError)
	fs.SetOutput(stderr)
	cfg, promptFile := agentFlags(fs, true)
	if err := fs.Parse(args); err != nil {
		return err
	}
	return runAgent(stdout, cfg, *promptFile)
}

func benchAgent(args []string, stdout io.Writer, stderr io.Writer) error {
	fs := flag.NewFlagSet("bench-agent", flag.ContinueOnError)
	fs.SetOutput(stderr)
	cfg, promptFile := agentFlags(fs, false)
	if err := fs.Parse(args); err != nil {
		return err
	}
	return runAgent(stdout, cfg, *promptFile)
}

func agentFlags(fs *flag.FlagSet, fixtureTools bool) (*agent.RunConfig, *string) {
	cfg := &agent.RunConfig{APIKey: os.Getenv("ANTHROPIC_API_KEY")}
	cfg.Model = firstNonEmpty(os.Getenv("MODEL"), os.Getenv("ANTHROPIC_MODEL"), "claude-sonnet-5")
	cfg.MCPURL = os.Getenv("MCP_URL")
	cfg.MaxSteps = 8
	cfg.UseFixtureTools = fixtureTools
	promptFile := fs.String("instruction", "", "prompt or instruction file")
	fs.StringVar(&cfg.Prompt, "prompt", "", "prompt text")
	fs.StringVar(&cfg.Model, "model", cfg.Model, "Anthropic model id")
	fs.StringVar(&cfg.MCPURL, "mcp-url", cfg.MCPURL, "remote MCP server URL")
	fs.IntVar(&cfg.MaxSteps, "max-steps", cfg.MaxSteps, "maximum tool loop steps")
	fs.BoolVar(&cfg.UseFixtureTools, "fixture-tools", cfg.UseFixtureTools, "enable local fixture tools")
	return cfg, promptFile
}

func runAgent(stdout io.Writer, cfg *agent.RunConfig, promptFile string) error {
	prompt, err := readPrompt(cfg.Prompt, promptFile)
	if err != nil {
		return err
	}
	cfg.Prompt = prompt
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	result, err := agent.Run(ctx, *cfg, o11y.FixtureBackend{})
	if err != nil {
		return err
	}
	_, err = fmt.Fprintln(stdout, result.Text)
	return err
}

func readPrompt(prompt string, path string) (string, error) {
	if strings.TrimSpace(prompt) != "" {
		return prompt, nil
	}
	if strings.TrimSpace(path) == "" {
		return "", fmt.Errorf("prompt or instruction file is required")
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return "", err
	}
	return string(data), nil
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return value
		}
	}
	return ""
}
