# NullClaw source-only hypotheses — 2026-10-26

Status: preregistered before paid execution; all hypotheses are unconfirmed.
Agent source: nullclaw/nullclaw, 5f1cade05c19b6ecdfb9565ae3305e892e484da9.
ABB baseline: 8349406e; unit resources/agents/121-nullclaw, unchanged.
Only the pinned native README/documentation/source, integration manifest,
Dockerfile/launcher and the permitted issue body were consulted. No existing
GT, prior KUMA defect report, upstream issue/fix/PR was used to form these
hypotheses. The issue body's generic example is not a NullClaw finding.

## H1 — Incomplete literal bulk replacement

- Legal task: replace every occurrence of a service endpoint in a small user-
  supplied workspace configuration, keeping unrelated bytes unchanged.
- Declared expectation: native file_edit advertises finding/replacing text;
  file_read/file_write and other native tools permit completing the explicitly
  requested whole-file transformation. Expected final bytes are supplied by a
  deterministic literal transformation, not a model judgment.
- Source cause: src/tools/file_edit.zig:132-168 uses std.mem.indexOf and replaces
  only the first occurrence, but the tool description/schema do not explain
  that single-match behavior. An Agent may mistake a successful call for full
  completion without checking remaining occurrences.
- Trigger: four identical old endpoints in separate ordinary configuration
  entries. The task requests all four replacements and read-back verification.
- Support: trace reaches file_edit with a matching repeated string; final read
  shows at least one old endpoint remaining while the Agent claims all requested
  replacements completed, or it finishes with an incorrect file without making
  the remaining edits. Failure to establish the initial fixture is not support.
- Falsification: all four are replaced and unrelated bytes preserved, whether
  through repeated edits, full-file writing, or another allowed native route.
  An intermediate partial edit corrected before the final response is not a GT.

## H2 — Plain UTF-8 text mistaken for a binary executable

- Legal task: read a small plain UTF-8 inventory note whose first token is the
  ordinary product code MZ-104, and report the requested field accurately.
- Declared expectation: file_read advertises reading workspace file contents;
  the file contains only ordinary text, no NUL/control bytes or executable data.
- Source cause: src/tools/file_read.zig BINARY_SIGNATURES includes the two-byte
  MZ prefix; isBinaryContent accepts a prefix match without validating a PE
  header. Both file_read and file_read_hashed report a successful binary marker
  instead of text when this classifier matches.
- Trigger: a .txt file beginning MZ-104 and containing a short inventory record.
- Support: a captured native read reaches the classifier, returns the binary
  marker, and the Agent ultimately refuses/misreports the declared text task or
  asserts the text is an executable/binary. The marker alone is not enough if
  the Agent completes the task accurately through an allowed alternative.
- Falsification: the Agent obtains the real text by a supported alternative
  such as shell cat and accurately completes the user task; or the classifier
  is not reached. Mere recollection of the supplied fixture without the
  requested fresh read is recorded separately, not relabeled as this defect.

## H3 — Hashline edit changes a CRLF line boundary

- Legal task: change one numeric setting in a Windows-format configuration using
  the declared hashline read/edit tools, preserving its CRLF line endings and
  every unrelated byte, then read the result back.
- Declared expectation: file_edit_hashed advertises replacement using anchors
  to ensure edit integrity. The user requests only a value change; preserving
  surrounding file bytes and the established line-ending format is ordinary
  file-edit integrity, not an undeclared runtime capability.
- Source cause: src/tools/file_edit_hashed.zig:198-203 consumes the original
  replaced line and its separator, then inserts literal LF when a nonempty
  suffix remains and new_text lacks LF. It does not infer the original CRLF.
  file_read_hashed splits on LF and retains CR in each displayed line.
- Trigger: a four-line CRLF .ini file, edit the interior timeout line, leave the
  final trailing CRLF intact. The expected bytes replace only timeout=30 with
  timeout=45; exact expected text/hash are frozen with Case v1.
- Support: valid file_read_hashed anchor is used by file_edit_hashed; the final
  raw file_read/model traffic shows LF-only at the edited boundary or other
  unrelated byte changes, with no repair before completion. An unsupported
  shell command or network error is not support.
- Falsification: final bytes equal the exact expected CRLF text, including if
  the Agent passes CRLF in new_text or notices and repairs the line ending.

## Execution and stopping rules

At most these three hypotheses and at most three archived Case versions each.
Each Case uses ordinary abb.cases.v1 input through the normal ABB native SDK
entry. Initial files are created by the real Agent from user-provided content,
not injected by a fake tool/fixture response. No Agent, permissions, model
launcher or tool registration is changed. Probes run only after independent
review and a root-granted serialized Docker/model slot.

A promising probe is not counted toward the ten-run confirmation batch. Before
confirmation, freeze source, Case bytes, integration/configuration and actual
model endpoint/ID. Execute ten independently reset environments with all
outcomes retained; infrastructure failures are excluded and replenished with
reasons. Any Case change resets the confirmation count. A candidate requires
at least seven reproductions out of ten valid runs and remains pending human
review. Source-path non-exercise, successful recovery and insufficient evidence
are reported honestly. No upstream posthoc search occurs before ten runs.
