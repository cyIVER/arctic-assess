// Literal no-model caller. Key is stdin-only and never printed.
package main
import("context";"encoding/json";"io";"os";"time";"github.com/Autumn-27/artex/nativeexec";"github.com/Autumn-27/norma/tool")
func main(){
 if len(os.Args)==2 && (os.Args[1]=="--literal-self-test" || os.Args[1]=="--public-output-self-test") {
  t,e:=nativeexec.Select("Bash");if e!=nil{os.Exit(2)}
  in:=json.RawMessage(`{"command":"printf '%s\\n' '{\"sdk_literal\":true}'","timeout_ms":1000}`)
  maxOutput:=1024
  if os.Args[1]=="--public-output-self-test" {
   in=json.RawMessage(`{"command":"python3 -c \"import os;os.write(1,b'PUBLIC_STDOUT_'+b'O'*8000);os.write(2,b'PUBLIC_STDERR_'+b'E'*8000)\"","timeout_ms":1000}`)
   maxOutput=16384
  }
  ctx,cancel:=context.WithTimeout(context.Background(),2*time.Second);defer cancel()
  if nativeexec.Validate(ctx,t,in)!=nil{os.Exit(2)}
  cwd,_:=os.Getwd();result,e:=t.Call(ctx,in,&tool.ToolContext{WorkingDir:cwd,Env:[]string{"PATH=/usr/bin:/bin","HOME=/nonexistent"},MaxOutputChars:maxOutput})
  if e!=nil || result.IsError{os.Exit(2)}
  if json.NewEncoder(os.Stdout).Encode(result)!=nil{os.Exit(2)};return
 }
 var in struct{Socket string;Key []byte;Request nativeexec.Request}
 d:=json.NewDecoder(io.LimitReader(os.Stdin,65537));d.DisallowUnknownFields()
 if d.Decode(&in)!=nil {os.Exit(2)}
 c,e:=nativeexec.NewClient(in.Socket,in.Key);if e!=nil{os.Exit(2)}
 ctx,cancel:=context.WithTimeout(context.Background(),18*time.Second);defer cancel()
 result,e:=c.Execute(ctx,in.Request);if e!=nil{os.Exit(2)}
 if json.NewEncoder(os.Stdout).Encode(struct{Version int `json:"version"`;Result any `json:"result"`}{1,result})!=nil{os.Exit(2)}
}
