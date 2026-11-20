//go:build artex_native_pg

package agent

import (
	"github.com/Autumn-27/norma/llm"
	"net/http"
)

// NativePGFixtureTransport replaces only HTTP for opt-in scripted integration tests.
func NativePGFixtureTransport(provider llm.Provider, transport http.RoundTripper) {
	provider.(*nativeRPC).client.Transport = transport
}
