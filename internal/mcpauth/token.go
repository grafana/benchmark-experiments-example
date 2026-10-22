package mcpauth

import (
	"context"
	"errors"
	"fmt"
	"io/fs"
	"net/http"
	"time"

	"golang.org/x/oauth2"
)

// ErrNotLoggedIn means there is no usable stored login for the MCP URL.
var ErrNotLoggedIn = errors.New("not logged in to the MCP server; run `watcherbench login`")

// refreshMargin forces a refresh when the token would expire during a run,
// since the Anthropic API calls the MCP server for the whole agent loop.
const refreshMargin = 5 * time.Minute

// AccessToken returns a valid access token for mcpURL, refreshing and
// re-saving the stored credentials when the token is close to expiry.
func AccessToken(ctx context.Context, hc *http.Client, path string, mcpURL string) (string, error) {
	creds, err := Load(path)
	if errors.Is(err, fs.ErrNotExist) {
		return "", ErrNotLoggedIn
	}
	if err != nil {
		return "", fmt.Errorf("load MCP credentials %s: %w", path, err)
	}
	if creds.MCPURL != mcpURL {
		return "", fmt.Errorf("stored login is for %s, not %s: %w", creds.MCPURL, mcpURL, ErrNotLoggedIn)
	}
	current := *creds.Token
	if !current.Expiry.IsZero() && time.Until(current.Expiry) < refreshMargin {
		current.Expiry = time.Now().Add(-time.Second)
	}
	ctx = context.WithValue(ctx, oauth2.HTTPClient, hc)
	tok, err := creds.config("", nil).TokenSource(ctx, &current).Token()
	if err != nil {
		return "", fmt.Errorf("refresh MCP token: %w (%w)", err, ErrNotLoggedIn)
	}
	if tok.AccessToken != creds.Token.AccessToken {
		creds.Token = tok
		if err := Save(path, creds); err != nil {
			return "", fmt.Errorf("save refreshed MCP token: %w", err)
		}
	}
	return tok.AccessToken, nil
}
