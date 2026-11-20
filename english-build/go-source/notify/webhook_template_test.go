package notify

import (
	"context"
	"reflect"
	"sort"
	"strings"
	"testing"
)

// This file locks down the generic Webhook template's **capability boundary**.
//
// This is the package's only place evaluating user-supplied strings as code, so specify what templates can
// and cannot do, and enforce those properties with tests. Otherwise adding a context
// method or a readFile FuncMap function could silently expand capabilities while the diff
// looks like a harmless helper.

// TestTemplateContextHasNoMethods is the most important assertion.
//
// text/template invokes exported methods ({{.Foo}} accesses fields or calls methods). Thus any
// reachable type with exported methods exposes those methods to template authors.
// This context deliberately contains only plain data: exported fields and no methods.
//
// Failure means a method was added to webhookTemplateData / webhookItem.
// Before permitting it, consider whether templates could use it to read unintended data.
func TestTemplateContextHasNoMethods(t *testing.T) {
	for _, v := range []any{webhookTemplateData{}, webhookItem{}} {
		typ := reflect.TypeOf(v)
		if n := typ.NumMethod(); n != 0 {
			var names []string
			for i := 0; i < n; i++ {
				names = append(names, typ.Method(i).Name)
			}
			t.Fatalf("%s 暴露了 %d 个方法（%s）：text/template 可以调用它们，"+
				"等于把这些方法的能力开放给了模板作者", typ.Name(), n, strings.Join(names, ", "))
		}
	}
}

// TestTemplateFuncsAreMinimal locks down the exposed function set.
//
// Every FuncMap entry adds a capability. Currently only json / jsons serialize values
// to JSON fragments: no file access, requests, or command execution.
func TestTemplateFuncsAreMinimal(t *testing.T) {
	var got []string
	for name := range webhookTemplateFuncs {
		got = append(got, name)
	}
	sort.Strings(got)
	want := []string{"json", "jsons"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("模板函数集合变了：得到 %v，期望 %v。新增函数前请确认它不会扩大能力面"+
			"（不能读写文件、不能发起网络请求、不能执行命令）", got, want)
	}
}

// TestTemplateCannotReachUnknownData covers out-of-bounds template access:
// accessing nonexistent data must fail rather than echo anything; errors must not expose internal data.
func TestTemplateCannotReachUnknownData(t *testing.T) {
	_, err := renderWebhookBody(`{"x": {{.Environment}}, "y": {{.Env}}}`, singleMsg())
	if err == nil {
		t.Fatal("访问不存在的字段应报错")
	}
	// Errors must not include actual context content such as vulnerability titles/summaries.
	for _, leak := range []string{"SQL注入", "参数 id"} {
		if strings.Contains(err.Error(), leak) {
			t.Errorf("模板错误泄露了消息内容 %q: %v", leak, err)
		}
	}
}

// TestTemplateRenderFailsPermanently: malformed templates are configuration errors, not repairable by retry.
// If retryable, each delivery with a bad template wastes three backoff rounds.
func TestTemplateRenderFailsPermanently(t *testing.T) {
	cfg := map[string]any{
		"url":           "https://example.com/hook",
		"body_template": `{{.Items.`,
	}
	if err := (webhookChannel{}).Validate(cfg); err == nil {
		t.Fatal("模板语法错误应在保存时就被拦下")
	}
	// Even direct delivery bypassing validation must classify this as permanent, not repeatedly retry.
	_, err := (webhookChannel{}).Send(context.Background(), cfg, singleMsg())
	if err == nil || !IsPermanent(err) {
		t.Fatalf("坏模板应判永久失败，得到 %v", err)
	}
}

// TestTemplateCanOnlyProduceJSON enforces valid JSON template output.
// It also prevents generating plaintext to trigger other protocols.
func TestTemplateCanOnlyProduceJSON(t *testing.T) {
	// Valid templates pass.
	ok := map[string]any{"url": "https://example.com/hook", "body_template": `{"t":{{json .Title}}}`}
	if err := (webhookChannel{}).Validate(ok); err != nil {
		t.Fatalf("合法模板应通过校验: %v", err)
	}
	// Reject non-JSON output rather than sending it unchanged.
	bad := map[string]any{"url": "http://127.0.0.1:1/hook", "body_template": `not json {{.Count}}`}
	_, err := (webhookChannel{}).Send(context.Background(), bad, singleMsg())
	if err == nil || !IsPermanent(err) {
		t.Fatalf("渲染出非 JSON 应判永久失败，得到 %v", err)
	}
	if !strings.Contains(err.Error(), "not valid JSON") {
		t.Errorf("错误信息应说明是 JSON 问题，得到 %v", err)
	}
}
