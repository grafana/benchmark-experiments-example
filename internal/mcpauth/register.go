package mcpauth

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
)

// Register performs RFC 7591 dynamic client registration for a public client
// whose only redirect URI is the loopback callback, and returns its client ID.
func Register(ctx context.Context, hc *http.Client, registrationURL string, redirectURI string) (string, error) {
	body, err := json.Marshal(map[string]any{
		"client_name":                "watcherbench",
		"redirect_uris":              []string{redirectURI},
		"grant_types":                []string{"authorization_code", "refresh_token"},
		"response_types":             []string{"code"},
		"token_endpoint_auth_method": "none",
	})
	if err != nil {
		return "", err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, registrationURL, bytes.NewReader(body))
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")
	resp, err := hc.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	var out struct {
		ClientID string `json:"client_id"`
	}
	if err := decodeJSON(resp, &out); err != nil {
		return "", err
	}
	if out.ClientID == "" {
		return "", errors.New("client registration returned no client_id")
	}
	return out.ClientID, nil
}
