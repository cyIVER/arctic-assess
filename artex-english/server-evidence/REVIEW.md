# Server English candidate review

**Partial translation, not completion.**

Changed 42 server paths. Final actual offline Go execution: {'pass': 21, 'fail': 0, 'skip': 2} top-level; {'pass': 40, 'fail': 0, 'skip': 0} subtests. No failed final tests. Two PostgreSQL-dependent tests skipped.

English mention tokens map to all nine backend kinds, retaining legacy aliases, supplied labels, validation, bounds and deduplication. Actual frontend-generated tokens are retained and tested. Initial hand-authored English contract tests failed before the alias patch; the generated fixture test was added afterward.

Remaining CJK: 1757 lines across 71 files. See remaining-nonenglish.json for every exact path/line/text and conservative classification. Much runtime prose, prompts, comments and test naming remains untranslated.

Approval producer and DB marker-classification changes remain in peer-owned intercept/db files; see report.json critical_peer_handoff. No source files outside server were written. No deployments, listeners, databases, models, credentials, global profiles, package installation or downloads were started. Cached Go compilation and focused tests actually ran; gofmt alone is not compilation evidence.

## Changed paths
- `server/assembly.go`
- `server/asset_intercept.go`
- `server/assets.go`
- `server/auth.go`
- `server/chat_mentions.go`
- `server/chat_mentions_english_test.go`
- `server/chat_mentions_test.go`
- `server/chatupload.go`
- `server/constraints_api.go`
- `server/conversations.go`
- `server/customtool.go`
- `server/dto.go`
- `server/engine.go`
- `server/engine_timeout.go`
- `server/findings_groups.go`
- `server/goals.go`
- `server/goals_api.go`
- `server/intent_intervention.go`
- `server/intercept.go`
- `server/intercept_detail_test.go`
- `server/mcpdiscover.go`
- `server/notify_api.go`
- `server/notify_api_test.go`
- `server/orchestration.go`
- `server/platform_tools.go`
- `server/scheduler.go`
- `server/server.go`
- `server/server_mgmt.go`
- `server/skill_upload_test.go`
- `server/skill_zip.go`
- `server/sync_scopesentry.go`
- `server/task_archives.go`
- `server/task_assets.go`
- `server/task_categories.go`
- `server/task_control.go`
- `server/task_intercept.go`
- `server/task_metadata.go`
- `server/task_resolution.go`
- `server/task_templates.go`
- `server/testdata/english_mentions.json`
- `server/update.go`
- `server/workspace.go`

## Remaining by file
- `server/assembly.go`: 11 CJK lines
- `server/asset_intercept.go`: 3 CJK lines
- `server/assets.go`: 1 CJK lines
- `server/assets_scope_test.go`: 2 CJK lines
- `server/auth_test.go`: 17 CJK lines
- `server/chat_llm_resolve_test.go`: 6 CJK lines
- `server/chat_mentions.go`: 3 CJK lines
- `server/chat_mentions_english_test.go`: 8 CJK lines
- `server/chat_mentions_test.go`: 23 CJK lines
- `server/constraints_api.go`: 18 CJK lines
- `server/conversations.go`: 8 CJK lines
- `server/core_test.go`: 1 CJK lines
- `server/customtool.go`: 35 CJK lines
- `server/engine.go`: 121 CJK lines
- `server/engine_emptyturn_test.go`: 39 CJK lines
- `server/engine_timeout.go`: 28 CJK lines
- `server/finding_retests.go`: 11 CJK lines
- `server/finding_retests_test.go`: 8 CJK lines
- `server/finding_traffic.go`: 7 CJK lines
- `server/finding_traffic_test.go`: 3 CJK lines
- `server/finding_workflow.go`: 12 CJK lines
- `server/finding_workflow_test.go`: 5 CJK lines
- `server/findings_groups.go`: 4 CJK lines
- `server/findings_groups_test.go`: 2 CJK lines
- `server/goals.go`: 26 CJK lines
- `server/goals_api.go`: 25 CJK lines
- `server/intent_intervention.go`: 10 CJK lines
- `server/intercept.go`: 2 CJK lines
- `server/intercept_detail_test.go`: 1 CJK lines
- `server/intercept_filter_test.go`: 2 CJK lines
- `server/intercept_live_test.go`: 8 CJK lines
- `server/intercept_review_test.go`: 3 CJK lines
- `server/llmpool.go`: 9 CJK lines
- `server/llmpool_test.go`: 1 CJK lines
- `server/llmretry.go`: 21 CJK lines
- `server/llmretry_test.go`: 2 CJK lines
- `server/logsink.go`: 2 CJK lines
- `server/manager.go`: 51 CJK lines
- `server/mcpdiscover.go`: 7 CJK lines
- `server/mgmt_test.go`: 2 CJK lines
- `server/native_reporter.go`: 1 CJK lines
- `server/notifier.go`: 156 CJK lines
- `server/notify_api.go`: 59 CJK lines
- `server/notify_api_test.go`: 231 CJK lines
- `server/orchestration.go`: 180 CJK lines
- `server/platform_tools.go`: 51 CJK lines
- `server/scheduler.go`: 14 CJK lines
- `server/server.go`: 226 CJK lines
- `server/server_mgmt.go`: 42 CJK lines
- `server/side_questions.go`: 13 CJK lines
- `server/skill_upload_test.go`: 31 CJK lines
- `server/sync_scopesentry.go`: 23 CJK lines
- `server/task_archive_package.go`: 5 CJK lines
- `server/task_archive_package_test.go`: 1 CJK lines
- `server/task_assets.go`: 1 CJK lines
- `server/task_categories_test.go`: 1 CJK lines
- `server/task_control.go`: 8 CJK lines
- `server/task_delete_barrier_test.go`: 1 CJK lines
- `server/task_intercept.go`: 5 CJK lines
- `server/task_llm.go`: 56 CJK lines
- `server/task_llm_test.go`: 1 CJK lines
- `server/task_metadata.go`: 3 CJK lines
- `server/task_metadata_test.go`: 1 CJK lines
- `server/task_templates_test.go`: 3 CJK lines
- `server/testdata/english_mentions.json`: 1 CJK lines
- `server/trigger_merge_test.go`: 11 CJK lines
- `server/triggers.go`: 4 CJK lines
- `server/update.go`: 49 CJK lines
- `server/update_test.go`: 29 CJK lines
- `server/webui_embed.go`: 1 CJK lines
- `server/webui_stub.go`: 1 CJK lines
