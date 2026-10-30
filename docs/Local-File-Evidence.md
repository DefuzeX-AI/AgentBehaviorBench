# Independent Local SDK file evidence and Judge budget

The independent/native SDK worker observes the declared Case workspace before
and after each input when `evaluation.file_evidence.track_files=true`. It does
not import KUMA, modify the workspace, replay tool calls, infer unobserved actions,
or upload the viewer's private replay archive. File observations and model/tool
traffic remain distinct evidence sources.

## Artifacts and integrity

Each executed step publishes `steps/NNNN/file-evidence.json`. Its changes identify
created, modified and deleted files. With `export_changed_files=true`, filtered
UTF-8 contents are retained in step-owned `file-content/*.json` artifacts; hashes
refer to the exact UTF-8 bytes, including original line endings. `upload_diff=true`
adds an explicitly observed text diff. Flags come from the trusted Agent manifest,
not the test Case. The Judge request binds both manifest and content artifacts by
SHA256 and byte size; the Local provider checks the content's inner digest too.

Snapshots are observations at input boundaries, not atomic filesystem transactions
or proof of the precise command used. An unchanged final file does not prove that
no intermediate changes occurred. Deleted files and baseline contents are retained
where the flags and limits permit them. Per-step omissions remain explicit.

The collector reads through descriptor-relative, no-follow POSIX file operations
in the Linux SDK controller. Symlinks, non-regular files, binary/non-UTF-8 contents,
credential-like paths/content and configured secrets are omitted rather than
rewritten as apparently original bytes. It skips `.git` and `.kuma` runtime trees.
The default limits are256KiB per file,8MiB per snapshot and1000 visited entries.
Read races, omissions or limit exhaustion mark the observation `partial`; absence
of an artifact is not a complete empty snapshot. A required missing/partial file
observation gives an `inconclusive` result before calling the Local model.

By default, Local Judge does not impose a character cap on evidence. An optional
positive `ABB_LOCAL_JUDGE_MAX_CHARS` returns inconclusive when exceeded; content
is never silently truncated to fit it. Provider context limits still apply.

## Explicit model reply budget

The default Local Judge reply budget remains2048 tokens. Reasoning models may
exhaust it before completing their JSON verdict. For a separately recorded run,
a caller may explicitly set:

```sh
export ABB_LOCAL_JUDGE_MAX_TOKENS=8192
export ABB_LOCAL_JUDGE_REASONING_EFFORT=low # only if supported by the provider
```

Valid values are integers from1 through32768. This controls the Judge request's
`max_tokens`; it changes no Agent model, tools, Judge system prompt, input guard,
strict response validator or verdict. Independent Local Case generation retains
its original2048-token budget. All raw replies are retained before validation;
`finish_reason=length` is rejected even when a parseable prefix appears to be a
complete object. A truncated `pass` prefix is not an accepted verdict, and a
failed submission is not automatically repeated.

A run using8192 must be labelled as an explicitly configured run, not a default
2048-token or unmodified-main pass. Agent onboarding and shared SDK changes belong
in separate PRs; tests of their composition must name both revisions. Keep the
original failed runs and use unchanged frozen inputs for dependency validation.

## Lossless streamed-trace presentation

The existing separately reviewed SDK fix in PR612 factors repeated JSONL context
fields into ordered blocks. Every original record, value type and order must
round-trip; malformed/unrepresentable streams stay raw. No tool output, text
chunk or event is removed, and original attachment bytes/hashes stay unchanged.
The exact model-facing view is retained at `judge/local-evidence-view.json`.
The lossless view reduces repetitive data without silently omitting evidence.
A configured character limit or the provider's context limit may still reject
a large request; the result is not automatically an Agent defect.
