import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import test from "node:test";
import { mentionKinds, mentionSearch, mentionToken, selectedMentions } from "./chat-mentions.ts";

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8");

test("mention categories and new tokens use English while keeping Unicode record text", () => {
  assert.deepEqual(mentionKinds.map((item) => item.label), [
    "Finding", "Asset", "Company", "Endpoint", "IP", "App", "Domain", "Subdomain", "Service",
  ]);
  assert.equal(mentionSearch("finding SQL injection").kind, "finding");
  const token = mentionToken({ kind: "finding", id: 42, label: "用户 supplied evidence" });
  assert.equal(token, "@[Finding#42 用户 supplied evidence]");
  assert.equal(selectedMentions(token)[0].label, "Finding #42 · 用户 supplied evidence");
  assert.equal(selectedMentions("@[漏洞#42 historical evidence]")[0].token, "@[漏洞#42 historical evidence]");
});

test("approval source detection accepts English and historical model markers", () => {
  const approvals = source("../components/approval-records.tsx");
  const match = /return (.+) \? "model" : "unknown";/.exec(approvals);
  const detect = new Function("row", `return ${match[1]} ? "model" : "unknown";`);
  assert.equal(detect({ reason: "[Model] Review required" }), "model");
  assert.equal(detect({ reason: "[模型] historical reason" }), "model");
  assert.equal(detect({ reason: "other" }), "unknown");
  assert.equal(detect({}), "unknown");
});

test("exploration graph controls and metadata are English", () => {
  const graph = source("../components/exploration-graph.tsx");
  for (const text of ['spawns: "Spawns"', 'label: "Root task"', 'label="Priority"', 'emptyHint = "No exploration data yet"', '"Copied" : "Copy"']) {
    assert.ok(graph.includes(text), `Missing English graph text: ${text}`);
  }
});

test("English document and explicit formatting defaults do not force Chinese locales", () => {
  assert.match(source("../app/layout.tsx"), /lang="en"/);
  assert.match(source("./utils.ts"), /locale = "en-US"/);
  function visit(url) {
    for (const entry of readdirSync(url, { withFileTypes: true })) {
      const child = new URL(entry.name + (entry.isDirectory() ? "/" : ""), url);
      if (entry.isDirectory()) visit(child);
      else if (/\.tsx?$/.test(entry.name)) {
        assert.doesNotMatch(readFileSync(child, "utf8"), /["']zh-CN["']/, child.pathname);
      }
    }
  }
  visit(new URL("../", import.meta.url));
});
