package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"runtime"
	"strings"
	"time"

	"github.com/grafana/benchmark-experiments-example/internal/mcpauth"
	"golang.org/x/oauth2"
)

var oauthHTTPClient = &http.Client{Timeout: 30 * time.Second}

func login(args []string, stdout io.Writer, stderr io.Writer) error {
	fs := flag.NewFlagSet("login", flag.ContinueOnError)
	fs.SetOutput(stderr)
	mcpURL := fs.String("mcp-url", os.Getenv("MCP_URL"), "hosted Grafana MCP server URL")
	scopes := fs.String("scopes", "grafana:read grafana:query", "space-separated OAuth scopes")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if strings.TrimSpace(*mcpURL) == "" {
		return errors.New("MCP_URL or --mcp-url is required")
	}
	path, err := mcpauth.DefaultPath()
	if err != nil {
		return err
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
	defer cancel()
	creds, err := mcpauth.Login(ctx, mcpauth.LoginOptions{
		MCPURL:      *mcpURL,
		Scopes:      strings.Fields(*scopes),
		HTTPClient:  oauthHTTPClient,
		OpenBrowser: openBrowser,
		Out:         stdout,
	})
	if err != nil {
		return err
	}
	if err := mcpauth.Save(path, creds); err != nil {
		return err
	}
	_, err = fmt.Fprintf(stdout, "Logged in to %s. Credentials saved to %s\n", *mcpURL, path)
	return err
}

// mcpToken picks the token Anthropic forwards to the MCP server for this run:
// an explicit MCP_ACCESS_TOKEN (e.g. injected into a benchmark container), else
// the stored OAuth login, else none, so servers without OAuth still work.
func mcpToken(ctx context.Context, mcpURL string, runTimeout time.Duration, stderr io.Writer) (string, error) {
	if tok := strings.TrimSpace(os.Getenv("MCP_ACCESS_TOKEN")); tok != "" {
		return tok, nil
	}
	tok, err := storedMCPToken(ctx, mcpURL, runTimeout)
	if errors.Is(err, mcpauth.ErrNotLoggedIn) {
		fmt.Fprintf(stderr, "warning: %v; connecting to %s without a token\n", err, mcpURL)
		return "", nil
	}
	if err != nil {
		return "", err
	}
	warnIfExpiresEarly(stderr, tok, runTimeout)
	return tok.AccessToken, nil
}

// printMCPToken prints a stored-login access token, for passing into
// environments that cannot run the browser login (MCP_ACCESS_TOKEN).
func printMCPToken(args []string, stdout io.Writer, stderr io.Writer) error {
	fs := flag.NewFlagSet("mcp-token", flag.ContinueOnError)
	fs.SetOutput(stderr)
	mcpURL := fs.String("mcp-url", os.Getenv("MCP_URL"), "hosted Grafana MCP server URL")
	minValid := fs.Duration("min-valid", 30*time.Minute, "refresh unless the token stays valid at least this long")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if strings.TrimSpace(*mcpURL) == "" {
		return errors.New("MCP_URL or --mcp-url is required")
	}
	ctx, cancel := context.WithTimeout(context.Background(), time.Minute)
	defer cancel()
	tok, err := storedMCPToken(ctx, *mcpURL, *minValid)
	if err != nil {
		return err
	}
	warnIfExpiresEarly(stderr, tok, *minValid)
	_, err = fmt.Fprintln(stdout, tok.AccessToken)
	return err
}

func storedMCPToken(ctx context.Context, mcpURL string, minValidity time.Duration) (*oauth2.Token, error) {
	path, err := mcpauth.DefaultPath()
	if err != nil {
		return nil, err
	}
	return mcpauth.AccessToken(ctx, oauthHTTPClient, path, mcpURL, minValidity)
}

// warnIfExpiresEarly flags tokens that expire before the run can finish:
// Anthropic cannot refresh them, so later MCP calls would fail.
func warnIfExpiresEarly(w io.Writer, tok *oauth2.Token, need time.Duration) {
	if tok.Expiry.IsZero() {
		return
	}
	if left := time.Until(tok.Expiry); left < need {
		fmt.Fprintf(w, "warning: MCP access token expires in %s, sooner than the %s needed; later MCP calls may fail\n",
			left.Round(time.Second), need)
	}
}

func openBrowser(url string) error {
	switch runtime.GOOS {
	case "darwin":
		return exec.Command("open", url).Start()
	case "windows":
		return exec.Command("rundll32", "url.dll,FileProtocolHandler", url).Start()
	default:
		return exec.Command("xdg-open", url).Start()
	}
}
