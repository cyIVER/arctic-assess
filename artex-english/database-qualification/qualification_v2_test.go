package qualification_test

import (
 "context"
 "database/sql"
 "encoding/json"
 "fmt"
 "os"
 "strconv"
 "testing"
 "time"

 "github.com/Autumn-27/artex/db"
 "github.com/Autumn-27/artex/intercept"
)

func must(t *testing.T, err error) { t.Helper(); if err != nil { t.Fatal(err) } }

func TestPrivatePostgresApprovalHistoryArchive(t *testing.T) {
 dsn := os.Getenv("ARTEX_PG_DSN"); if dsn == "" { t.Fatal("required private fixture missing") }
 d, err := db.Open(dsn); must(t,err); defer d.Close()
 must(t,d.EnsureLLMRecordsTable()); must(t,d.EnsureLLMUsageTable())
 var listen,auth string
 must(t,d.QueryRow(`SHOW listen_addresses`).Scan(&listen)); if listen!="" { t.Fatal("TCP listener configured") }
 must(t,d.QueryRow(`SELECT string_agg(type || ':' || auth_method, ',' ORDER BY line_number) FROM pg_hba_file_rules WHERE error IS NULL`).Scan(&auth))
 task,err:=d.CreateTaskWithOptions("private approval archive qualification","preserve original multilingual evidence",db.TaskCreateOptions{});must(t,err)
 scope:=strconv.FormatInt(task.ID,10)
 must(t,d.SetPaused(task.ID,true))
 rule,err:=d.CreateInterceptRule("qualification supplied 用户","tool_name","string","Read","deny","",1,true,false,0,"deny");must(t,err)
 type evidence struct { Name string `json:"name"`; ID int64 `json:"id"`; Reason string `json:"reason"`; Source string `json:"source"`; Created time.Time `json:"created"`; Decided time.Time `json:"decided"` }
 rows:=[]evidence{}
 for _,tc:=range []struct{name,reason,want string; rule int64}{
  {"english","[Model] Original 用户 evidence","model",0},
  {"legacy","[模型] Original 用户 evidence","model",0},
  {"rule_english","[Model] rule 用户 evidence","rule",rule.ID},
  {"rule_legacy","[模型] rule 用户 evidence","rule",rule.ID},
  {"unknown","Original 用户 evidence","unknown",0},
  {"embedded","evidence [Model] 用户","unknown",0},
  {"persisted_override","[Model] explicit 用户","unknown",0},
 } {
  id,e:=d.CreateDecidedIntercept(tc.rule,0,scope,"worker","Read",[]byte(`{"path":"用户.txt"}`),"allowed",tc.reason);must(t,e)
  if tc.name=="persisted_override" { _,e=d.Exec(`UPDATE intercept_pending SET decision_source='unknown' WHERE id=$1`,id);must(t,e) }
  var source,reason string; var created,decided time.Time
  must(t,d.QueryRow(`SELECT decision_source,reason,created_at,decided_at FROM intercept_pending WHERE id=$1`,id).Scan(&source,&reason,&created,&decided))
  if source!=tc.want || reason!=tc.reason { t.Fatalf("insert %s: %s %s",tc.name,source,reason) }
  rows=append(rows,evidence{tc.name,id,reason,source,created,decided})
 }
 // Exercise production SQL fallback, not only the Go insertion classifier.
 for _,r:=range rows { if r.Name!="persisted_override" { _,err=d.Exec(`UPDATE intercept_pending SET decision_source='' WHERE id=$1`,r.ID);must(t,err) } }
 for source,want:=range map[string]int{"model":2,"rule":2,"unknown":3} {
  got,total,e:=d.ListTaskInterceptsPage(scope,1,100,db.InterceptApprovalFilter{Status:"allowed",DecisionSource:source});must(t,e)
  if total!=want || len(got)!=want { t.Fatalf("SQL classifier %s count %d/%d want %d",source,total,len(got),want) }
  for _,r:=range got { if r.DecisionSource!=source {t.Fatal("history source mismatch")} }
 }
 // Schema backfill executes through the actual idempotent Open path.
 d2,e:=db.Open(dsn);must(t,e);must(t,d2.Close())
 for _,r:=range rows { var source,reason string;must(t,d.QueryRow(`SELECT decision_source,reason FROM intercept_pending WHERE id=$1`,r.ID).Scan(&source,&reason));if source!=r.Source||reason!=r.Reason {t.Fatalf("backfill changed %s",r.Name)} }
 pending,err:=d.CreateInterceptPending(0,0,scope,"worker","Read",[]byte(`{}`),"[Model] pending 用户",&db.InterceptAudit{EffectiveAction:"ask",ExecutionStatus:"pending"});must(t,err)
 archive,err:=d.QueueTaskArchive(task.ID);must(t,err)
 claimed,err:=d.ClaimTaskArchiveJob(t.Context());must(t,err);if claimed==nil||claimed.ID!=archive.ID {t.Fatal("archive claim mismatch")}
 snapshot,err:=d.SnapshotTaskArchive(task.ID);must(t,err)
 // Remove only the historical source field to represent old archive manifests.
 var archived []map[string]any;must(t,json.Unmarshal(snapshot.Tables["intercept_pending"],&archived))
 for _,r:=range archived {if int64(r["id"].(float64))!=rows[6].ID {delete(r,"decision_source")} }
 snapshot.Tables["intercept_pending"],err=json.Marshal(archived);must(t,err)
 must(t,d.CompleteTaskArchive(archive.ID,snapshot,"qualification-metadata-only.tar.zst","not-a-filesystem-artifact",0,0))
 var count int;must(t,d.QueryRow(`SELECT count(*) FROM intercept_pending WHERE task_id=$1`,scope).Scan(&count));if count!=0 {t.Fatal("hot approvals not compacted")}
 _,err=d.QueueTaskArchiveRestore(archive.ID);must(t,err);claimed,err=d.ClaimTaskArchiveJob(t.Context());must(t,err);if claimed==nil||claimed.State!=db.Restoring {t.Fatal("restore claim mismatch")}
 warnings,err:=d.RestoreTaskArchive(archive.ID,snapshot,600);must(t,err)
 must(t,d.CompleteTaskArchiveRestore(archive.ID))
 // New independent SQL connection reads committed rows and exact historical times.
 independent,err:=sql.Open("pgx",dsn);must(t,err);defer independent.Close()
 for _,r:=range rows {
  var source,reason,status string;var created,decided time.Time
  must(t,independent.QueryRow(`SELECT decision_source,reason,status,created_at,decided_at FROM intercept_pending WHERE id=$1`,r.ID).Scan(&source,&reason,&status,&created,&decided))
  if source!=r.Source||reason!=r.Reason||status!="allowed"||!created.Equal(r.Created)||!decided.Equal(r.Decided) {t.Fatalf("archive lost evidence %+v got %s %s %s %s %s",r,source,reason,status,created,decided)}
 }
 var pendingStatus,pendingReason,action string
 must(t,independent.QueryRow(`SELECT status,reason,audit->>'effective_action' FROM intercept_pending WHERE id=$1`,pending).Scan(&pendingStatus,&pendingReason,&action))
 if pendingStatus!="timeout"||pendingReason!="Approval timed out while the task was archived"||action!="deny" {t.Fatal("pending archive not fail closed")}
 // Actual production interception with real PG, injected deterministic reviewer (no model).
 i:=intercept.New(d);must(t,d.SetBool("llm_judge_enabled",true))
 calls:=0;i.SetReviewer(func(context.Context,int64,string,intercept.ReviewInput)(intercept.Decision,error){calls++;return intercept.Decision{Action:"allow"},nil})
 dec,ok:=i.Judge(t.Context(),"Read",json.RawMessage(`{}`));if !ok||calls!=1||dec.Message!="[Model] Allowed" {t.Fatal("real PG Judge defaults")}
 ctx:=intercept.WithTaskContext(t.Context(),scope,"worker",nil);i.Log(ctx,0,dec,"Read",[]byte(`{}`),"allowed")
 ctx,cancel:=context.WithCancel(t.Context());var emitted db.Activity
 ctx=intercept.WithTaskContext(ctx,scope,"worker",func(a db.Activity){emitted=a;cancel()})
 if i.HandleAsk(ctx,0,intercept.Decision{Action:"ask",Message:"[Model] Requires human approval"},"Read",[]byte(`{}`)) {t.Fatal("cancel allowed")}
 var detail struct{PendingID int64 `json:"pending_id"`};must(t,json.Unmarshal([]byte(emitted.Detail),&detail))
 if emitted.Summary!=fmt.Sprintf("Tool Read requests approval (#%d)",detail.PendingID)||detail.PendingID==0 {t.Fatal("summary mismatch")}
 var cancelReason,cancelAction,execution string
 must(t,independent.QueryRow(`SELECT status,reason,audit->>'decision_reason',audit->>'effective_action',audit->>'execution_status' FROM intercept_pending WHERE id=$1`,detail.PendingID).Scan(&pendingStatus,&pendingReason,&cancelReason,&cancelAction,&execution));if pendingStatus!="denied"||pendingReason!="[Model] Requires human approval"||cancelReason!="Work was cancelled"||cancelAction!="deny"||execution!="not_executed" {t.Fatalf("cancellation/evidence contract: status=%s reason=%s decision=%s action=%s execution=%s",pendingStatus,pendingReason,cancelReason,cancelAction,execution)}
 proof:=map[string]any{"rows":rows,"scope":scope,"pending_id":pending,"pending_archive_status":"timeout","pending_archive_action":action,"warnings":warnings,"listen_addresses":listen,"hba":auth,"judge_reviewer_calls":calls,"judge_message":dec.Message,"ask_summary":emitted.Summary,"ask_cancel_status":pendingStatus,"ask_original_reason":pendingReason,"ask_cancel_reason":cancelReason,"ask_cancel_action":cancelAction,"ask_execution_status":execution,"archive_hot_count":count,"independent_committed_readback":true}
 raw,err:=json.MarshalIndent(proof,"","  ");must(t,err);must(t,os.WriteFile(os.Getenv("QUAL_EVIDENCE")+"/sql-proof.json",raw,0600))
}
