// Package mcpauth implements the OAuth 2.1 authorization code flow (PKCE,
// dynamic client registration, loopback redirect) that hosted MCP servers such
// as https://mcp.grafana.com require, and stores the resulting tokens.
package mcpauth

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"slices"
	"strings"
)

// Metadata is the subset of the RFC 9728 protected resource and RFC 8414
// authorization server documents needed to log in.
type Metadata struct {
	Resource        string
	AuthURL         string
	TokenURL        string
	RegistrationURL string
}

type protectedResource struct {
	Resource             string   `json:"resource"`
	AuthorizationServers []string `json:"authorization_servers"`
}

type authServer struct {
	AuthorizationEndpoint string   `json:"authorization_endpoint"`
	TokenEndpoint         string   `json:"token_endpoint"`
	RegistrationEndpoint  string   `json:"registration_endpoint"`
	CodeChallengeMethods  []string `json:"code_challenge_methods_supported"`
}

// Discover resolves the OAuth endpoints for an MCP server URL.
func Discover(ctx context.Context, hc *http.Client, mcpURL string) (Metadata, error) {
	prmURL, err := wellKnown(mcpURL, "oauth-protected-resource")
	if err != nil {
		return Metadata{}, err
	}
	var prm protectedResource
	if err := getJSON(ctx, hc, prmURL, &prm); err != nil {
		return Metadata{}, fmt.Errorf("protected resource metadata: %w", err)
	}
	if len(prm.AuthorizationServers) == 0 {
		return Metadata{}, errors.New("protected resource metadata lists no authorization servers")
	}
	asURL, err := wellKnown(prm.AuthorizationServers[0], "oauth-authorization-server")
	if err != nil {
		return Metadata{}, err
	}
	var as authServer
	if err := getJSON(ctx, hc, asURL, &as); err != nil {
		return Metadata{}, fmt.Errorf("authorization server metadata: %w", err)
	}
	if !slices.Contains(as.CodeChallengeMethods, "S256") {
		return Metadata{}, errors.New("authorization server does not support PKCE S256")
	}
	md := Metadata{
		Resource:        prm.Resource,
		AuthURL:         as.AuthorizationEndpoint,
		TokenURL:        as.TokenEndpoint,
		RegistrationURL: as.RegistrationEndpoint,
	}
	return md, md.validate()
}

func (m Metadata) validate() error {
	if m.Resource == "" {
		return errors.New("protected resource metadata has no resource")
	}
	for _, raw := range []string{m.AuthURL, m.TokenURL, m.RegistrationURL} {
		if err := requireHTTPS(raw); err != nil {
			return err
		}
	}
	return nil
}

// wellKnown inserts /.well-known/<name> between the host and the path
// (RFC 8414 section 3.1), e.g. https://h/mcp -> https://h/.well-known/<name>/mcp.
func wellKnown(raw string, name string) (string, error) {
	if err := requireHTTPS(raw); err != nil {
		return "", err
	}
	u, err := url.Parse(raw)
	if err != nil {
		return "", err
	}
	u.Path = "/.well-known/" + name + strings.TrimSuffix(u.Path, "/")
	u.RawPath, u.RawQuery, u.Fragment = "", "", ""
	return u.String(), nil
}

func requireHTTPS(raw string) error {
	u, err := url.Parse(raw)
	if err != nil {
		return fmt.Errorf("invalid url %q: %w", raw, err)
	}
	if u.Scheme != "https" || u.Host == "" {
		return fmt.Errorf("url %q must be an absolute https url", raw)
	}
	return nil
}

func getJSON(ctx context.Context, hc *http.Client, rawURL string, out any) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, rawURL, nil)
	if err != nil {
		return err
	}
	req.Header.Set("Accept", "application/json")
	resp, err := hc.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	return decodeJSON(resp, out)
}

// decodeJSON accepts any 2xx: registration servers answer 201 or 200.
func decodeJSON(resp *http.Response, out any) error {
	body, err := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	if err != nil {
		return err
	}
	if resp.StatusCode/100 != 2 {
		return fmt.Errorf("%s: status %d: %s", resp.Request.URL, resp.StatusCode, strings.TrimSpace(string(body)))
	}
	return json.Unmarshal(body, out)
}
