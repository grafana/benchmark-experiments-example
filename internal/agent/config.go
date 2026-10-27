package agent

import (
	"errors"
	"fmt"
	"net/url"
	"strings"
)

type RunConfig struct {
	APIKey          string
	Model           string
	Prompt          string
	MCPURL          string
	MCPToken        string
	MaxSteps        int
	UseFixtureTools bool
}

func (c RunConfig) Validate() error {
	if strings.TrimSpace(c.APIKey) == "" {
		return errors.New("ANTHROPIC_API_KEY is required")
	}
	if strings.TrimSpace(c.Prompt) == "" {
		return errors.New("prompt is required")
	}
	if len(c.Prompt) > 6000 {
		return errors.New("prompt must be <= 6000 bytes")
	}
	if err := validateModel(c.Model); err != nil {
		return err
	}
	return validateMCPURL(c.MCPURL)
}

func validateModel(model string) error {
	if strings.TrimSpace(model) == "" {
		return errors.New("model is required")
	}
	if len(model) > 120 {
		return errors.New("model must be <= 120 bytes")
	}
	return nil
}

func validateMCPURL(raw string) error {
	if strings.TrimSpace(raw) == "" {
		return nil
	}
	parsed, err := url.Parse(raw)
	if err != nil {
		return fmt.Errorf("invalid mcp url: %w", err)
	}
	if parsed.Scheme != "http" && parsed.Scheme != "https" {
		return errors.New("mcp url must use http or https")
	}
	return nil
}
