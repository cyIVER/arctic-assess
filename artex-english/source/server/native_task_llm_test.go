package server

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/Autumn-27/artex/agent"
	"github.com/Autumn-27/artex/db"
	"github.com/Autumn-27/norma/llm"
)

// This is a provider error fixture, not model inference or worker acceptance.
// The marker is a trusted Go provider property and only REDUCES authority.
type nativeTaskErrorFixture struct{ scriptedLLMProvider }

func (*nativeTaskErrorFixture) NativeInferenceOnly() bool { return true }

func TestNativeTaskCompleteNeverRetriesOrFailsOver(t *testing.T) {
	for _, tc := range []struct {
		name, message              string
		legacyCalls, legacyExhaust int
	}{
		{"transient", "HTTP status 503: synthetic unavailable", 2, 0},
		{"quota", "openai: status 402: insufficient_quota", 1, 1},
	} {
		for _, native := range []bool{false, true} {
			name := tc.name + "/legacy"
			if native {
				name = tc.name + "/native"
			}
			t.Run(name, func(t *testing.T) {
				sentinel := errors.New(tc.message)
				base := &scriptedLLMProvider{err: sentinel}
				var provider llm.Provider = base
				nativeFixture := &nativeTaskErrorFixture{scriptedLLMProvider{err: sentinel}}
				if native {
					provider = nativeFixture
				}
				exhausts := 0
				selections := 0
				hooks := taskLLMStreamHooks{
					current: func() (taskLLMSelection, error) {
						selections++
						return taskLLMSelection{profileID: 11, provider: provider, retry: agent.RetryConfig{StreamAttempts: 1, StreamInterval: time.Millisecond}}, nil
					},
					exhaust: func(taskLLMSelection, error) (db.TaskLLMTransition, error) {
						exhausts++
						return db.TaskLLMTransition{}, nil
					},
				}
				_, _, _, err := completeTaskLLM(context.Background(), "21", llm.CompletionRequest{Messages: []llm.Message{llm.UserText("SYNTHETIC NO TARGET")}}, hooks)
				if !errors.Is(err, sentinel) {
					t.Fatalf("original error lost: %v", err)
				}
				calls := base.calls
				wantCalls, wantExhaust := tc.legacyCalls, tc.legacyExhaust
				if native {
					calls = nativeFixture.calls
					wantCalls = 1
					wantExhaust = 0
				}
				if calls != wantCalls || exhausts != wantExhaust || selections != 1 {
					t.Fatalf("calls=%d exhausts=%d selections=%d; want calls=%d exhausts=%d", calls, exhausts, selections, wantCalls, wantExhaust)
				}
			})
		}
	}
}

func TestNativeTaskStreamNeverRetriesOrFailsOver(t *testing.T) {
	for _, tc := range []struct {
		name, message              string
		legacyCalls, legacyExhaust int
	}{
		{"transient", "HTTP status 503: synthetic unavailable", 2, 0},
		{"quota", "openai: status 402: insufficient_quota", 1, 1},
	} {
		for _, native := range []bool{false, true} {
			name := tc.name + "/legacy"
			if native {
				name = tc.name + "/native"
			}
			t.Run(name, func(t *testing.T) {
				sentinel := errors.New(tc.message)
				base := &scriptedLLMProvider{err: sentinel}
				var provider llm.Provider = base
				nativeFixture := &nativeTaskErrorFixture{scriptedLLMProvider{err: sentinel}}
				if native {
					provider = nativeFixture
				}
				exhausts := 0
				selections := 0
				hooks := taskLLMStreamHooks{
					current: func() (taskLLMSelection, error) {
						selections++
						return taskLLMSelection{profileID: 11, provider: provider, retry: agent.RetryConfig{StreamAttempts: 1, StreamInterval: time.Millisecond}}, nil
					},
					exhaust: func(taskLLMSelection, error) (db.TaskLLMTransition, error) {
						exhausts++
						return db.TaskLLMTransition{}, nil
					},
				}
				_, err := collectTaskLLMStream(streamTaskLLM(context.Background(), "21", llm.CompletionRequest{Messages: []llm.Message{llm.UserText("SYNTHETIC NO TARGET")}}, hooks))
				if !errors.Is(err, sentinel) {
					t.Fatalf("original error lost: %v", err)
				}
				calls := base.calls
				wantCalls, wantExhaust := tc.legacyCalls, tc.legacyExhaust
				if native {
					calls = nativeFixture.calls
					wantCalls = 1
					wantExhaust = 0
				}
				if calls != wantCalls || exhausts != wantExhaust || selections != 1 {
					t.Fatalf("calls=%d exhausts=%d selections=%d; want calls=%d exhausts=%d", calls, exhausts, selections, wantCalls, wantExhaust)
				}
			})
		}
	}
}
