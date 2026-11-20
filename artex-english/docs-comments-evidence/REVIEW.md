# Comments and historical changelog review

## Outcome
Historical changelog 0.3.15–0.3.2 is translated, with zero CJK prose outside preserved inline code. Existing English Unreleased is byte-identical. All release headings/dates, heading levels, entry indentation/counts, URLs, inline-code multisets per original line, fences and line count are unchanged. See `changelog-proof.json` for per-release counts and mutation tests.

161 comments were translated in 20 Go files. All 228 owned Go files, including tests, retain **every non-comment byte and every literal byte exactly**, not merely normalized tokens. Directives are unchanged. See `verification.json`, before/after SHA256 manifests and `owned-changes.patch`.

## Verification limits
The Python lexical guard passed its positive and deliberate identifier/literal mutation fixtures before source edits. Structural negative tests also reject removed release headings, changed URLs and removed entries. No cached goparse executable was located; builds were forbidden. **No Go parse or compile was executed, and the requested same-byte parse-positive fixture remains unperformed.** Do not label this as compiled or fully syntax-qualified evidence.

## Unfinished language scope
Comment translation is partial. `remaining-classified.json` gives exact current paths, lines, category and text, including unfinished explanatory comments, protected documentation references/UTF-8 examples, unchanged multilingual test fixtures and out-of-scope runtime/SQL literals. All interception CJK is in preserved literals, not comments. Seven changelog lines retain only protected inline identifiers, examples, paths or evidence.

## Handoff
`report.json` lists exact changed source paths and counts. Only CHANGELOG and comments in owned Go files were changed; all new evidence is under this directory. Frozen baseline/reports from prior workers were not edited. There is no git repository at this task root, so the recorded owned-subset baseline and diff are the comparison source. Continue from the unfinished-comment category without changing behavior strings, SQL, fixtures, directives or other workers' files.

Lessons: replace comment spans, not global CJK matches; pin historical structure and inline code before edits; locate a cached parser before promising parse verification under no-build constraints.
