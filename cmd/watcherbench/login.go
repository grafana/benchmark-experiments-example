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

	"github.com/wei-chincall/grafana-oss-talks/internal/mcpauth"
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

// mcpToken returns the stored OAuth access token for mcpURL, refreshing it if needed.
func mcpToken(ctx context.Context, mcpURL string) (string, error) {
	path, err := mcpauth.DefaultPath()
	if err != nil {
		return "", err
	}
	return mcpauth.AccessToken(ctx, oauthHTTPClient, path, mcpURL)
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
