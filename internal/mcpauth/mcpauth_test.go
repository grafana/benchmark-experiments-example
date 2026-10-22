package mcpauth

import (
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"path/filepath"
	"testing"
	"time"

	"golang.org/x/oauth2"
)

// fakeServer implements just enough of the hosted MCP OAuth surface.
type fakeServer struct {
	*httptest.Server
	challenge string
	resource  string
	refreshes int
}

func newFakeServer(t *testing.T) *fakeServer {
	f := &fakeServer{}
	mux := http.NewServeMux()
	f.Server = httptest.NewTLSServer(mux)
	t.Cleanup(f.Close)
	mux.HandleFunc("/.well-known/oauth-protected-resource/mcp/stack.grafana.net", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, map[string]any{"resource": f.URL + "/mcp", "authorization_servers": []string{f.URL + "/mcp/stack.grafana.net"}})
	})
	mux.HandleFunc("/.well-known/oauth-authorization-server/mcp/stack.grafana.net", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, map[string]any{
			"authorization_endpoint":           f.URL + "/oauth/authorize?grafana_url=https%3A%2F%2Fstack.grafana.net",
			"token_endpoint":                   f.URL + "/oauth/token",
			"registration_endpoint":            f.URL + "/oauth/register",
			"code_challenge_methods_supported": []string{"S256"},
		})
	})
	mux.HandleFunc("/oauth/register", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusCreated)
		writeJSON(w, map[string]any{"client_id": "client-123"})
	})
	mux.HandleFunc("/oauth/token", f.token(t))
	return f
}

func (f *fakeServer) token(t *testing.T) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if err := r.ParseForm(); err != nil {
			t.Fatal(err)
		}
		switch r.Form.Get("grant_type") {
		case "authorization_code":
			sum := sha256.Sum256([]byte(r.Form.Get("code_verifier")))
			if base64.RawURLEncoding.EncodeToString(sum[:]) != f.challenge || r.Form.Get("code") != "auth-code" {
				http.Error(w, `{"error":"invalid_grant"}`, http.StatusBadRequest)
				return
			}
			f.resource = r.Form.Get("resource")
			writeJSON(w, map[string]any{"access_token": "access-1", "refresh_token": "refresh-1", "token_type": "Bearer", "expires_in": 3600})
		case "refresh_token":
			f.refreshes++
			writeJSON(w, map[string]any{"access_token": "access-2", "refresh_token": "refresh-2", "token_type": "Bearer", "expires_in": 3600})
		}
	}
}

// browser plays the user approving consent: it follows the auth URL's
// redirect_uri back to the loopback listener.
func (f *fakeServer) browser(t *testing.T) func(string) error {
	return func(authURL string) error {
		u, err := url.Parse(authURL)
		if err != nil {
			return err
		}
		q := u.Query()
		if q.Get("grafana_url") == "" || q.Get("code_challenge_method") != "S256" || q.Get("client_id") != "client-123" {
			t.Errorf("unexpected auth url %s", authURL)
		}
		f.challenge = q.Get("code_challenge")
		go func() {
			resp, err := http.Get(q.Get("redirect_uri") + "?code=auth-code&state=" + url.QueryEscape(q.Get("state")))
			if err == nil {
				resp.Body.Close()
			}
		}()
		return nil
	}
}

func writeJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(v)
}

func TestLoginThenAccessToken(t *testing.T) {
	f := newFakeServer(t)
	mcpURL := f.URL + "/mcp/stack.grafana.net"
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	creds, err := Login(ctx, LoginOptions{
		MCPURL: mcpURL, Scopes: []string{"grafana:read"},
		HTTPClient: f.Client(), OpenBrowser: f.browser(t), Out: io.Discard,
	})
	if err != nil {
		t.Fatal(err)
	}
	if creds.Token.AccessToken != "access-1" || creds.ClientID != "client-123" {
		t.Fatalf("unexpected credentials %+v", creds)
	}
	if f.resource != f.URL+"/mcp" {
		t.Fatalf("token request resource = %q", f.resource)
	}
	path := filepath.Join(t.TempDir(), "creds.json")
	if err := Save(path, creds); err != nil {
		t.Fatal(err)
	}
	tok, err := AccessToken(ctx, f.Client(), path, mcpURL)
	if err != nil || tok != "access-1" || f.refreshes != 0 {
		t.Fatalf("AccessToken = %q, %v, refreshes %d", tok, err, f.refreshes)
	}
}

func TestAccessTokenRefreshesNearExpiry(t *testing.T) {
	f := newFakeServer(t)
	path := filepath.Join(t.TempDir(), "creds.json")
	creds := Credentials{
		MCPURL: "https://mcp.example/mcp", ClientID: "client-123", TokenURL: f.URL + "/oauth/token",
		Token: &oauth2.Token{AccessToken: "old", RefreshToken: "refresh-1", Expiry: time.Now().Add(time.Minute)},
	}
	if err := Save(path, creds); err != nil {
		t.Fatal(err)
	}
	tok, err := AccessToken(context.Background(), f.Client(), path, creds.MCPURL)
	if err != nil || tok != "access-2" || f.refreshes != 1 {
		t.Fatalf("AccessToken = %q, %v, refreshes %d", tok, err, f.refreshes)
	}
	saved, err := Load(path)
	if err != nil || saved.Token.RefreshToken != "refresh-2" {
		t.Fatalf("refreshed token not saved: %+v, %v", saved.Token, err)
	}
}

func TestAccessTokenNotLoggedIn(t *testing.T) {
	path := filepath.Join(t.TempDir(), "creds.json")
	if _, err := AccessToken(context.Background(), http.DefaultClient, path, "https://a/mcp"); !errors.Is(err, ErrNotLoggedIn) {
		t.Fatalf("missing file: got %v", err)
	}
	creds := Credentials{MCPURL: "https://a/mcp", Token: &oauth2.Token{AccessToken: "x"}}
	if err := Save(path, creds); err != nil {
		t.Fatal(err)
	}
	if _, err := AccessToken(context.Background(), http.DefaultClient, path, "https://b/mcp"); !errors.Is(err, ErrNotLoggedIn) {
		t.Fatalf("other url: got %v", err)
	}
}

func TestWellKnown(t *testing.T) {
	got, err := wellKnown("https://mcp.grafana.com/mcp/stack.grafana.net", "oauth-protected-resource")
	if err != nil || got != "https://mcp.grafana.com/.well-known/oauth-protected-resource/mcp/stack.grafana.net" {
		t.Fatalf("wellKnown = %q, %v", got, err)
	}
	if _, err := wellKnown("http://mcp.grafana.com/mcp", "x"); err == nil {
		t.Fatal("expected http url to be rejected")
	}
}

func TestParseCallback(t *testing.T) {
	cases := map[string]url.Values{
		"state mismatch": {"state": {"other"}, "code": {"c"}},
		"error":          {"state": {"s"}, "error": {"access_denied"}},
		"no code":        {"state": {"s"}},
	}
	for name, q := range cases {
		if res := parseCallback(q, "s"); res.err == nil {
			t.Errorf("%s: expected error", name)
		}
	}
	if res := parseCallback(url.Values{"state": {"s"}, "code": {"c"}}, "s"); res.err != nil || res.code != "c" {
		t.Errorf("valid callback: %+v", res)
	}
}
