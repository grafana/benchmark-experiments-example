package agent

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"log"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/grafana/agento11y/go/agento11y"
	aisdk "github.com/grafana/ai-sdk"
	"github.com/grafana/ai-sdk/provider"
	"github.com/wei-chincall/grafana-oss-talks/internal/telemetry"
)

const (
	agentName    = "watcherbench"
	agentVersion = "0.1.0"

	// shutdownTimeout bounds telemetry flush/shutdown. It is intentionally a
	// fresh background timeout rather than the request context: a canceled or
	// timed-out request must not also abort flushing the generation it just
	// produced.
	shutdownTimeout = 5 * time.Second

	conversationTitleMaxRunes = 80
)

// generationTelemetry is the Agent Observability generation for one Run()
// call, plus the process-wide OTel providers it exports spans/metrics
// through.
type generationTelemetry struct {
	shutdownOTel func(context.Context) error
	client       *agento11y.Client
	gen          *agento11y.GenerationRecorder
}

// startGenerationTelemetry configures OTel and the agento11y client, then
// starts one generation for this call. It returns the context to run the
// model call under (carrying the generation's span) and a handle to record
// the outcome and close everything down afterward.
func startGenerationTelemetry(ctx context.Context, cfg RunConfig) (context.Context, *generationTelemetry) {
	shutdownOTel, err := telemetry.SetupOTel(ctx, agentName)
	if err != nil {
		log.Printf("agento11y: otel setup failed, metrics/traces will not be recorded: %v", err)
	}

	// Config{} (not DefaultConfig()) so the AGENTO11Y_* env vars (protocol,
	// endpoint, auth) aren't overridden by DefaultConfig's grpc/localhost values.
	client := agento11y.NewClient(agento11y.Config{})

	genCtx, gen := client.StartGeneration(ctx, agento11y.GenerationStart{
		ConversationID:    newConversationID(),
		ConversationTitle: conversationTitle(cfg.Prompt),
		AgentName:         agentName,
		AgentVersion:      agentVersion,
		Model:             agento11y.ModelRef{Provider: "anthropic", Name: NormalizeModel(cfg.Model)},
		SystemPrompt:      systemPrompt,
	})

	return genCtx, &generationTelemetry{shutdownOTel: shutdownOTel, client: client, gen: gen}
}

// recordError closes the generation with the model call's error.
func (t *generationTelemetry) recordError(err error) {
	t.gen.SetCallError(err)
	t.gen.End()
}

// recordResult closes the generation with its result.
func (t *generationTelemetry) recordResult(prompt string, result *aisdk.GenerateTextResult) {
	t.gen.SetResult(agento11y.Generation{
		Input:         []agento11y.Message{agento11y.UserTextMessage(prompt)},
		Output:        []agento11y.Message{agento11y.AssistantTextMessage(result.Text)},
		ResponseID:    result.Response.ID,
		ResponseModel: result.Response.ModelID,
		StopReason:    string(result.FinishReason.Unified),
		Usage:         tokenUsage(result.TotalUsage),
	}, nil)
	t.gen.End()
}

// close flushes and shuts down the agento11y client and the OTel providers.
// It always runs, independent of whether the request context is still live.
func (t *generationTelemetry) close() {
	if err := t.gen.Err(); err != nil {
		log.Printf("agento11y: generation export error: %v", err)
	}

	shutdownCtx, cancel := context.WithTimeout(context.Background(), shutdownTimeout)
	defer cancel()

	if err := t.client.Shutdown(shutdownCtx); err != nil {
		log.Printf("agento11y: client shutdown failed: %v", err)
	}
	if err := t.shutdownOTel(shutdownCtx); err != nil {
		log.Printf("agento11y: otel shutdown failed: %v", err)
	}
}

func tokenUsage(usage provider.Usage) agento11y.TokenUsage {
	return agento11y.TokenUsage{
		InputTokens:           intOrZero(usage.InputTokens.Total),
		OutputTokens:          intOrZero(usage.OutputTokens.Total),
		CacheReadInputTokens:  intOrZero(usage.InputTokens.CacheRead),
		CacheWriteInputTokens: intOrZero(usage.InputTokens.CacheWrite),
		ReasoningTokens:       intOrZero(usage.OutputTokens.Reasoning),
	}
}

func intOrZero(p *int) int64 {
	if p == nil {
		return 0
	}
	return int64(*p)
}

// newConversationID generates a per-run conversation identifier. Each
// watcherbench invocation is a standalone, single-turn interaction, so the
// conversation boundary is the CLI run itself.
func newConversationID() string {
	var raw [8]byte
	if _, err := rand.Read(raw[:]); err != nil {
		return "conv_unknown"
	}
	return "conv_" + hex.EncodeToString(raw[:])
}

// conversationTitle derives a short, human-readable conversation title from
// the prompt so it doesn't fall back to an opaque ID in the Agent
// Observability UI.
func conversationTitle(prompt string) string {
	title := strings.Join(strings.Fields(prompt), " ")
	if utf8.RuneCountInString(title) <= conversationTitleMaxRunes {
		return title
	}
	runes := []rune(title)
	return string(runes[:conversationTitleMaxRunes]) + "..."
}
