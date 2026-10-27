package o11y

import (
	"errors"
	"fmt"
	"strings"
)

const maxQueryLength = 512

func ValidateQuery(query string) error {
	q := strings.TrimSpace(query)
	if q == "" {
		return errors.New("query is required")
	}
	if len(q) > maxQueryLength {
		return fmt.Errorf("query must be <= %d bytes", maxQueryLength)
	}
	if looksLikeSecret(q) {
		return errors.New("query must not contain token-like values")
	}
	return nil
}

func ValidateDashboardPatch(input DashboardPatchInput) error {
	if strings.TrimSpace(input.UID) == "" {
		return errors.New("dashboard uid is required")
	}
	if input.PanelID <= 0 {
		return errors.New("panel id must be positive")
	}
	return ValidateQuery(input.Query)
}

func looksLikeSecret(value string) bool {
	lowered := strings.ToLower(value)
	return strings.Contains(lowered, "bearer ") || strings.Contains(lowered, "sk-")
}
