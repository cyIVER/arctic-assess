package agent

import (
	"context"
	"io"
	"net/http"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func TestNativeQueuedPhaseDenialsDoNotReserve(t *testing.T) {
	for _, mode := range []string{"cancel", "revoke", "expiry"} {
		t.Run(mode, func(t *testing.T) {
			p, binder, ctx, req, _ := admittedRoleFixture(t)
			started := make(chan struct{})
			release := make(chan struct{})
			firstDone := make(chan error, 1)
			secondDone := make(chan error, 1)
			var calls atomic.Int32
			p.client.Transport = roleRoundTrip(func(r *http.Request) (*http.Response, error) {
				calls.Add(1)
				close(started)
				select {
				case <-release:
				case <-r.Context().Done():
					return nil, r.Context().Err()
				}
				return &http.Response{StatusCode: 200, Header: http.Header{"Content-Type": []string{"application/json"}}, Body: io.NopCloser(strings.NewReader(roleSyntheticResponse))}, nil
			})
			go func() { _, _, _, e := p.Complete(ctx, req); firstDone <- e }()
			select {
			case <-started:
			case <-time.After(time.Second):
				t.Fatal("positive inflight not reached")
			}
			if mode == "expiry" {
				p.policy.phase.ExpiresAt = time.Now().Add(80 * time.Millisecond)
			}
			waiting, cancel := context.WithCancel(ctx)
			defer cancel()
			go func() { _, _, _, e := p.Complete(waiting, req); secondDone <- e }()
			select {
			case e := <-secondDone:
				t.Fatalf("valid overlap rejected instead of queueing: %v", e)
			case <-time.After(20 * time.Millisecond):
			}
			s := p.policy.phase.state
			s.mu.Lock()
			reserved, counter := s.reservedBytes, s.calls
			s.mu.Unlock()
			if counter != 1 {
				t.Fatalf("queued request charged %d calls", counter)
			}
			switch mode {
			case "cancel":
				cancel()
			case "revoke":
				binder.RevokeNativeRolePhase()
			}
			select {
			case e := <-secondDone:
				if e == nil {
					t.Fatal("queued invalidation admitted")
				}
			case <-time.After(time.Second):
				t.Fatal("queued denial did not wake")
			}
			close(release)
			select {
			case <-firstDone:
			case <-time.After(time.Second):
				t.Fatal("first request did not settle")
			}
			s.mu.Lock()
			defer s.mu.Unlock()
			if calls.Load() != 1 || s.calls != 1 || s.reservedBytes != reserved || s.inFlight {
				t.Fatalf("queued denial changed accounting: HTTP=%d calls=%d bytes=%d/%d inflight=%v", calls.Load(), s.calls, s.reservedBytes, reserved, s.inFlight)
			}
		})
	}
}
