package mcpauth

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"sync"
	"time"

	"golang.org/x/oauth2"
)

// LoginOptions configures an interactive browser login.
type LoginOptions struct {
	MCPURL      string
	Scopes      []string
	HTTPClient  *http.Client
	OpenBrowser func(authURL string) error
	Out         io.Writer
}

type callbackResult struct {
	code string
	err  error
}

// Login discovers the server's OAuth endpoints, registers a public client,
// sends the user through the browser consent page, and exchanges the returned
// code (with PKCE) for tokens.
func Login(ctx context.Context, opts LoginOptions) (Credentials, error) {
	md, err := Discover(ctx, opts.HTTPClient, opts.MCPURL)
	if err != nil {
		return Credentials{}, err
	}
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return Credentials{}, err
	}
	defer ln.Close()
	redirectURL := fmt.Sprintf("http://%s/callback", ln.Addr())
	clientID, err := Register(ctx, opts.HTTPClient, md.RegistrationURL, redirectURL)
	if err != nil {
		return Credentials{}, fmt.Errorf("register client: %w", err)
	}
	creds := Credentials{MCPURL: opts.MCPURL, ClientID: clientID, AuthURL: md.AuthURL, TokenURL: md.TokenURL}
	cfg := creds.config(redirectURL, opts.Scopes)
	verifier, state := oauth2.GenerateVerifier(), oauth2.GenerateVerifier()
	resource := oauth2.SetAuthURLParam("resource", md.Resource)
	authURL := cfg.AuthCodeURL(state, oauth2.S256ChallengeOption(verifier), resource)
	promptBrowser(opts, authURL)
	code, err := awaitCode(ctx, ln, state)
	if err != nil {
		return Credentials{}, err
	}
	ctx = context.WithValue(ctx, oauth2.HTTPClient, opts.HTTPClient)
	creds.Token, err = cfg.Exchange(ctx, code, oauth2.VerifierOption(verifier), resource)
	if err != nil {
		return Credentials{}, fmt.Errorf("exchange authorization code: %w", err)
	}
	return creds, nil
}

func promptBrowser(opts LoginOptions, authURL string) {
	fmt.Fprintf(opts.Out, "Open this URL to authorize watcherbench:\n\n  %s\n\n", authURL)
	if opts.OpenBrowser == nil {
		return
	}
	if err := opts.OpenBrowser(authURL); err != nil {
		fmt.Fprintf(opts.Out, "Could not open a browser (%v); open the URL manually.\n", err)
	}
}

func awaitCode(ctx context.Context, ln net.Listener, state string) (string, error) {
	results := make(chan callbackResult, 1)
	srv := &http.Server{Handler: callbackHandler(state, results), ReadHeaderTimeout: 10 * time.Second}
	go srv.Serve(ln)
	defer srv.Close()
	select {
	case r := <-results:
		return r.code, r.err
	case <-ctx.Done():
		return "", fmt.Errorf("waiting for browser authorization: %w", ctx.Err())
	}
}

func callbackHandler(state string, results chan<- callbackResult) http.Handler {
	var once sync.Once
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/callback" {
			http.NotFound(w, r)
			return
		}
		res := parseCallback(r.URL.Query(), state)
		if res.err != nil {
			http.Error(w, "Authorization failed. Return to the terminal for details.", http.StatusBadRequest)
		} else {
			fmt.Fprintln(w, "Authorization complete. You can close this tab.")
		}
		once.Do(func() { results <- res })
	})
}

func parseCallback(q url.Values, state string) callbackResult {
	if q.Get("state") != state {
		return callbackResult{err: errors.New("OAuth callback state mismatch")}
	}
	if e := q.Get("error"); e != "" {
		return callbackResult{err: fmt.Errorf("authorization failed: %s: %s", e, q.Get("error_description"))}
	}
	code := q.Get("code")
	if code == "" {
		return callbackResult{err: errors.New("OAuth callback has no code")}
	}
	return callbackResult{code: code}
}
