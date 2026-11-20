package agent
import("context";"encoding/json";"os";"strings";"testing";"time";"net/http";"bytes";"io";"github.com/Autumn-27/norma/llm")
func TestNativeGoPythonSynthetic(t *testing.T){
 raw:=os.Getenv("SYNTHETIC_PORTS");if raw==""{t.Skip("retained Python jsonschema unavailable; not cross-language proof")}
 ports:=map[string]string{};if e:=json.Unmarshal([]byte(raw),&ports);e!=nil{t.Fatal(e)}
 provider:=func(name,key string)*nativeRPC{u:="http://127.0.0.1:"+ports[name]+"/artex/native/v1/complete";c:=ConfigFrom("codex-native","gpt-6.1-sol",u,"","");c.Native=&NativeRPCPolicy{Endpoint:u,ServiceKey:key,BudgetMode:"time/bytes/calls",Timeout:2*time.Second,MaxCalls:8};p,e:=newNativeRPC(c);if e!=nil{t.Fatal(e)};return p}
 req:=llm.CompletionRequest{Messages:[]llm.Message{llm.UserText("SYNTHETIC NO TARGET")},System:[]string{"SYNTHETIC NO TARGET"}}
 p:=provider("text",strings.Repeat("f",64))
 for _,hint:=range []int{32768,8192,1500}{req.MaxTokens=hint;m,s,u,e:=p.Complete(context.Background(),req);if e!=nil||m.Text()!="SYNTHETIC NO TARGET"||s!="end_turn"||u.InputTokens!=3||u.OutputTokens!=4{t.Fatalf("hint %d: %v %v %v %v",hint,m,s,u,e)};t.Logf("real Go->Python hint=%d synthetic usage=3/4 not token-cap enforcement",hint)}
 // Decode exact Norma wire types, rather than replacing them with a mock request.
 var history llm.CompletionRequest
 if e:=json.Unmarshal([]byte(`{"messages":[{"role":"user","content":[{"type":"text","text":"fixture"}]},{"role":"assistant","content":[{"type":"tool_use","id":"call_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","name":"synthetic_echo","input":{"text":"fixture"}}]},{"role":"user","content":[{"type":"tool_result","tool_use_id":"call_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","content":[{"type":"text","text":"synthetic result"}]}]}],"tools":[{"name":"synthetic_echo","description":"no target fixture","input_schema":{"type":"object","properties":{"text":{"type":"string"}},"required":["text"],"additionalProperties":false}}]}`),&history);e!=nil{t.Fatal(e)}
 m,s,_,e:=provider("tool",strings.Repeat("f",64)).Complete(context.Background(),history);if e!=nil||s!="tool_use"||len(m.Content)!=1||m.Content[0].Name!="synthetic_echo"{t.Fatalf("Norma history/tool roundtrip: %v %v %v",m,s,e)};t.Log("real Go->Python correlated tool history + schema + proposal passed; no tool executed")
 if _,_,_,e:=provider("tool",strings.Repeat("f",64)).Complete(context.Background(),req);e==nil{t.Fatal("unknown output tool accepted")}
 history.Messages[2].Content[0].ToolUseID="unknown"
 if _,_,_,e:=p.Complete(context.Background(),history);e==nil{t.Fatal("uncorrelated result accepted")}
 if _,_,_,e:=provider("text",strings.Repeat("e",64)).Complete(context.Background(),req);e==nil{t.Fatal("wrong auth accepted")}
 b:=provider("budget",strings.Repeat("f",64));if _,_,_,e:=b.Complete(context.Background(),req);e!=nil{t.Fatal(e)};if _,_,_,e:=b.Complete(context.Background(),req);e==nil{t.Fatal("server budget ignored")}
 ctx,cancel:=context.WithTimeout(context.Background(),80*time.Millisecond);defer cancel();if _,_,_,e:=provider("cancel",strings.Repeat("f",64)).Complete(ctx,req);e==nil{t.Fatal("cancel accepted")}
 u:="http://127.0.0.1:"+ports["text"]+"/artex/native/v1/complete";h,_:=http.NewRequest("POST",u,bytes.NewBufferString(`{"protocol":"wrong"}`));h.Header.Set("Content-Type","application/json");h.Header.Set("Authorization","Bearer "+strings.Repeat("f",64));res,e:=(&http.Client{Timeout:time.Second}).Do(h);if e!=nil{t.Fatal(e)};io.Copy(io.Discard,res.Body);res.Body.Close();if res.StatusCode!=400{t.Fatalf("invalid contract status %d",res.StatusCode)}
 t.Log("real Go->Python auth/contract/unknown-tool/budget/cancel rejection passed")
}
