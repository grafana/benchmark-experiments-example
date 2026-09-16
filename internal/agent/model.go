package agent

import "strings"

const defaultModel = "claude-sonnet-5"

func NormalizeModel(model string) string {
	trimmed := strings.TrimSpace(model)
	if trimmed == "" {
		return defaultModel
	}
	return strings.TrimPrefix(trimmed, "anthropic/")
}
