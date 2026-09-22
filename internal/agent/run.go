package agent

import (
	"context"

	aisdk "github.com/grafana/ai-sdk"
	"github.com/grafana/ai-sdk/provider"
	"github.com/grafana/ai-sdk/providers/anthropic"
	"github.com/wei-chincall/grafana-oss-talks/internal/o11y"
)

type Result struct {
	Text      string
	Steps     int
	ToolCalls []string
}

func Run(ctx context.Context, cfg RunConfig, backend o11y.Backend) (Result, error) {
	if err := cfg.Validate(); err != nil {
		return Result{}, err
	}

	genCtx, tel := startGenerationTelemetry(ctx, cfg)
	defer tel.close()

	opts, err := options(cfg, backend)
	if err != nil {
		return Result{}, err
	}
	model := anthropic.New(cfg.APIKey, NormalizeModel(cfg.Model))

	result, err := aisdk.GenerateText(genCtx, model, opts...)
	if err != nil {
		tel.recordError(err)
		return Result{}, err
	}
	tel.recordResult(cfg.Prompt, result)

	return Result{Text: result.Text, Steps: len(result.Steps), ToolCalls: toolNames(result.ToolCalls)}, nil
}

func options(cfg RunConfig, backend o11y.Backend) ([]aisdk.GenerateOption, error) {
	opts := []aisdk.GenerateOption{
		aisdk.WithSystem(systemPrompt),
		aisdk.WithModelMessages(provider.UserText(cfg.Prompt)),
		aisdk.WithStopWhen(aisdk.StepCountIs(maxSteps(cfg.MaxSteps))),
		aisdk.WithTemperature(0),
	}
	if cfg.UseFixtureTools {
		tools, err := Tools(backend)
		if err != nil {
			return nil, err
		}
		opts = append(opts, aisdk.WithTools(tools))
	}
	if cfg.MCPURL != "" {
		opts = append(opts, aisdk.WithProviderOptions(mcpOptions(cfg.MCPURL)))
	}
	return opts, nil
}

func mcpOptions(rawURL string) anthropic.AnthropicOptions {
	return anthropic.AnthropicOptions{MCPServers: []anthropic.MCPServer{{
		Name: "o11y-bench-grafana",
		URL:  rawURL,
		ToolConfiguration: &anthropic.MCPToolConfiguration{
			Enabled: true,
		},
	}}}
}

func maxSteps(value int) int {
	if value <= 0 {
		return 8
	}
	if value > 20 {
		return 20
	}
	return value
}

func toolNames(calls []aisdk.ToolCall) []string {
	names := make([]string, 0, len(calls))
	for _, call := range calls {
		names = append(names, call.ToolName)
	}
	return names
}
