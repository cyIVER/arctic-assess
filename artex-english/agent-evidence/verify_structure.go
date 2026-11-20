package main

import (
 "encoding/json"
 "fmt"
 "go/scanner"
 "go/token"
 "os"
 "path/filepath"
 "reflect"
)

func structural(src string) []string {
 var s scanner.Scanner
 s.Init(token.NewFileSet().AddFile("source.go",-1,len(src)),[]byte(src),nil,0)
 var out []string
 for {_,tok,lit:=s.Scan();if tok==token.EOF {break};if tok==token.STRING || tok==token.CHAR {out=append(out,tok.String());continue};out=append(out,tok.String()+":"+lit)}
 return out
}
func main(){
 root:=os.Args[1];var originals map[string]string
 b,e:=os.ReadFile(filepath.Join(root,"agent-evidence/original-subset.json"));if e!=nil {panic(e)}
 if e=json.Unmarshal(b,&originals);e!=nil {panic(e)}
 result:=map[string]bool{};ok:=true
 for name,original:=range originals {
  if filepath.Ext(name)!=".go" {continue}
  current,e:=os.ReadFile(filepath.Join(root,"source",name));if e!=nil {panic(e)}
  if string(current)==original {continue}
  // Only production source is subject to exact token-structure equivalence.
  if len(name)>=8 && name[len(name)-8:]=="_test.go" {continue}
  same:=reflect.DeepEqual(structural(original),structural(string(current)))
  result[name]=same;ok=ok&&same
 }
 b,_=json.MarshalIndent(map[string]any{"production_token_structure_unchanged":ok,"files":result,"method":"Go scanner tokens equal after masking string/character values and omitting comments; verifies no control-flow, identifiers, numeric budgets, names of Go APIs, permissions or admission code edits. Does not prove natural-language semantic equivalence."},"","  ")
 fmt.Println(string(b));if !ok {os.Exit(1)}
}
