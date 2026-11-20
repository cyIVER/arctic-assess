package server

import (
	"bytes"
	"encoding/json"
	"github.com/Autumn-27/artex/agent"
	"github.com/Autumn-27/artex/db"
	"net/http"
	"strconv"
)

func (s *Server) nativeAdmissionStatus(w http.ResponseWriter, r *http.Request) {
	// Defense in depth: this read can ultimately open the synthetic executor key.
	if !verifyJWT(extractToken(r), s.jwtKey) {
		writeErr(w, 401, "unauthorized")
		return
	}
	deny := func() { writeErr(w, 503, "native configuration observation unavailable") }
	if r.Method != "GET" || r.URL.RawQuery != "" || r.ContentLength != 0 {
		deny()
		return
	}
	t, ok := s.m.Task(r.PathValue("id"))
	if !ok {
		deny()
		return
	}
	id, e := strconv.ParseInt(t.ID, 10, 64)
	if e != nil {
		deny()
		return
	}
	pg, e := db.OpenReadOnlyCatalog(r.Context(), s.m.nativeCatalogDSN)
	if e != nil {
		deny()
		return
	}
	defer pg.Close()
	task, e := pg.GetTask(id)
	if e != nil || task == nil || task.ExplorationID != t.ExpID || task.Status != "running" || task.Paused || len(task.LLMProfileIDs) != 0 || task.ActiveLLMProfileID != nil {
		deny()
		return
	}
	available, e := pg.NativeGlobalSourceAvailable()
	if e != nil || !available {
		deny()
		return
	}
	// Pin the actual installed provider/config until observation completes. Never
	// call FromEnv, a provider factory, task.current, or NativeTaskProvider here.
	s.cfgMu.Lock()
	defer s.cfgMu.Unlock()
	if !s.llmOn {
		deny()
		return
	}
	observation, e := agent.ObserveNativeAdmission(r.Context(), s.llmProv, s.llmCfg, id, t.ExpID)
	if e != nil {
		deny()
		return
	}
	req := agent.NativeCatalogRequest{TaskID: id, ExplorationID: t.ExpID, ExecutorID: observation.ExecutorID, NetworkPolicyID: observation.NetworkPolicyID, FixtureOrigin: observation.FixtureOrigin, ExpectedGlobal: agent.NativeCatalogGlobal{Format: s.llmCfg.Provider(), Model: s.llmCfg.Model, Endpoint: s.llmCfg.BaseURL}}
	raw, _ := json.Marshal(req)
	var out bytes.Buffer
	if agent.RunNativeCatalogPreflight(r.Context(), pg, s.llmCfg, bytes.NewReader(raw), &out) != nil {
		deny()
		return
	}
	var catalog agent.NativeCatalogResult
	if json.Unmarshal(out.Bytes(), &catalog) != nil || len(catalog.Roles) != len(observation.Catalogs) {
		deny()
		return
	}
	for _, role := range catalog.Roles {
		if observation.Catalogs[role.Role] != role.CatalogSHA256 {
			deny()
			return
		}
	}
	// All auth, T/E, source, role, and catalog checks precede executor.key.
	if agent.VerifyNativeExecutorConfiguration(s.llmProv) != nil {
		deny()
		return
	}
	if _, e = agent.ObserveNativeAdmission(r.Context(), s.llmProv, s.llmCfg, id, t.ExpID); e != nil {
		deny()
		return
	}
	observation.ExecutorConfigVerified = true
	w.Header().Set("Cache-Control", "no-store")
	writeJSON(w, 200, observation)
}
