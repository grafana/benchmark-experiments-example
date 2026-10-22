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

// refreshSlack covers the time between fetching the token and the first MCP call.
const refreshSlack = time.Minute

// AccessToken returns a token for mcpURL that stays valid for at least
// minValidity when the server allows it, refreshing and re-saving the stored
// credentials otherwise. Anthropic receives the token once per run and cannot
// refresh it, so minValidity should cover the whole run. The returned token's
// Expiry can still be sooner if the server issues shorter-lived tokens.
func AccessToken(ctx context.Context, hc *http.Client, path string, mcpURL string, minValidity time.Duration) (*oauth2.Token, error) {
	creds, err := Load(path)
	if errors.Is(err, fs.ErrNotExist) {
		return nil, ErrNotLoggedIn
	}
	if err != nil {
		return nil, fmt.Errorf("load MCP credentials %s: %w", path, err)
	}
	if creds.MCPURL != mcpURL {
		return nil, fmt.Errorf("stored login is for %s, not %s: %w", creds.MCPURL, mcpURL, ErrNotLoggedIn)
	}
	current := *creds.Token
	if !current.Expiry.IsZero() && time.Until(current.Expiry) < minValidity+refreshSlack {
		current.Expiry = time.Now().Add(-time.Second)
	}
	ctx = context.WithValue(ctx, oauth2.HTTPClient, hc)
	tok, err := creds.config("", nil).TokenSource(ctx, &current).Token()
	if err != nil {
		return nil, fmt.Errorf("refresh MCP token (run `watcherbench login` again): %w", err)
	}
	if tok.AccessToken != creds.Token.AccessToken {
		creds.Token = tok
		if err := Save(path, creds); err != nil {
			return nil, fmt.Errorf("save refreshed MCP token: %w", err)
		}
	}
	return tok, nil
}
