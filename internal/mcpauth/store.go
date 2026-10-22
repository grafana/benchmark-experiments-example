package mcpauth

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"

	"golang.org/x/oauth2"
)

// Credentials is what a login persists: the registered client, the endpoints
// needed to refresh, and the current token. The file holds a refresh token, so
// it is written with owner-only permissions.
type Credentials struct {
	MCPURL   string        `json:"mcp_url"`
	ClientID string        `json:"client_id"`
	AuthURL  string        `json:"auth_url"`
	TokenURL string        `json:"token_url"`
	Token    *oauth2.Token `json:"token"`
}

// DefaultPath is the per-user credentials file, e.g.
// ~/Library/Application Support/watcherbench/mcp-oauth.json on macOS.
func DefaultPath() (string, error) {
	dir, err := os.UserConfigDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(dir, "watcherbench", "mcp-oauth.json"), nil
}

// Save writes the credentials atomically with 0600 permissions.
func Save(path string, c Credentials) error {
	if c.Token == nil {
		return errors.New("credentials have no token")
	}
	data, err := json.MarshalIndent(c, "", "  ")
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return err
	}
	tmp, err := os.CreateTemp(filepath.Dir(path), ".mcp-oauth-*.json")
	if err != nil {
		return err
	}
	defer os.Remove(tmp.Name())
	if _, err := tmp.Write(data); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	return os.Rename(tmp.Name(), path)
}

// Load reads credentials written by Save.
func Load(path string) (Credentials, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return Credentials{}, err
	}
	var c Credentials
	if err := json.Unmarshal(data, &c); err != nil {
		return Credentials{}, err
	}
	if c.Token == nil {
		return Credentials{}, errors.New("stored credentials have no token")
	}
	return c, nil
}

func (c Credentials) config(redirectURL string, scopes []string) *oauth2.Config {
	return &oauth2.Config{
		ClientID:    c.ClientID,
		RedirectURL: redirectURL,
		Scopes:      scopes,
		Endpoint: oauth2.Endpoint{
			AuthURL:   c.AuthURL,
			TokenURL:  c.TokenURL,
			AuthStyle: oauth2.AuthStyleInParams,
		},
	}
}
