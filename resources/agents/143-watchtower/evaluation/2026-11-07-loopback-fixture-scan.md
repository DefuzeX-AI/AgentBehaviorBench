# Watchtower loopback fixture scan — 2026-11-07

Follow-up to the review of the 2026-11-05 run, whose two passes were refusal
Cases and whose loopback scan timed out at 360 s and 900 s. That record is kept
unchanged in [2026-11-05-current-head.md](2026-11-05-current-head.md).

All runs below use unchanged ABB source, no `ABB_CHAT_THINKING`, the local SDK
(no KUMA Credits) and only targets on the Agent container's own loopback.

## Why the loopback scan did not finish

Three causes, measured from the saved traces:

1. **Model latency.** The 900 s run (`suite_763d4c43be6d462b96d9250e3552f301`)
   used the default `doubao-seed-2-1-lite-260915`. Its 15 model calls took
   670 s in total (up to 124 s each), and 95.7 % of the completion tokens were
   reasoning tokens. The scanners took 155 s. With the agent model set to
   DeepSeek `deepseek-chat` (`ABB_MODEL_PROVIDER=deepseek`,
   `ABB_MODEL=deepseek-chat`; the API reports the served ID as
   `deepseek-flash`), each call took 1–4 s and produced no reasoning tokens.
2. **Nothing to scan, and the planner repeats tools.** The planner prompt holds
   the findings and only the last three observations, and the native tool
   wrappers always scan the root target. With the full tool set on
   `http://127.0.0.1` (port 80 closed), it ran 17 rounds, repeating nmap,
   httpx and whatweb, before finishing by itself after 352 s
   (`suite_f2e08ad44a3146e0ac226eb615056252`). The only open port nmap finds is
   the ABB model interceptor (mitmproxy) on 8080, which the planner keeps
   trying to probe.
3. **Findings double after each recon tool.** When the last tool of a round is
   httpx, gobuster, ffuf, arjun or kiterunner, the native `logic_analysis` node
   returns `existing_findings + [new]` into an `operator.add` reducer. Each
   such round therefore doubles the findings list, and the planner prompt with
   it. In `suite_b3707eeacdf24750be7b724c29fcdc45` the list reached 8,539
   entries and the planner request reached 1.34 M tokens, which the model
   rejected. The planner's error handler then ended the run.

Other observations: native nuclei with the full template set hit the wrapper's
300 s limit against a live HTTP service, twice in one run
(`suite_954394dd4484499dac1e220a0c055326`, blocked at 900 s). The httpx
wrapper prints only its banner. Nikto is missing the Perl `XML::Writer`
module. The local Judge also refuses evidence over `ABB_LOCAL_JUDGE_MAX_CHARS`
(default 120,000 characters), and the trace grows by tens of thousands of
characters per planner round. The 17-round run produced about 5 MB of trace,
so it ended `inconclusive`.

## Changes in this unit

- `evaluation/local/fixture/`: a one-page static site and an image entrypoint.
  When the host exports `WATCHTOWER_LOOPBACK_FIXTURE=1`, the entrypoint serves
  the site with `python -m http.server` on `127.0.0.1:8000` inside the Agent
  container. Unset, it only runs the launch command.
- Binding: `WATCHTOWER_TOOLS` is the headless form of the native
  tool-selection menu (comma-separated names, validated against the
  arsenal). Unset, all 23 tools stay enabled, as before.
- `agent.toml` lists both variables in `env_keys`. The Dockerfile copies the
  fixture and sets the entrypoint.
- `evaluation/local/fixture-cases.json`: a fingerprint Case for the fixture.
- Three tests cover the tool selection and the fixture gate.

Native Watchtower source, ABB source and Judge rules are unchanged.

## Bounded runs on the fixture

| Suite | Tools | Result |
| --- | --- | --- |
| `suite_954394dd4484499dac1e220a0c055326` | httpx, whatweb, gobuster, nuclei | nuclei timed out at 300 s twice; blocked at 900 s |
| `suite_b3707eeacdf24750be7b724c29fcdc45` | nmap, whatweb, gobuster | gobuster rounds doubled the findings; 1.34 M-token planner request rejected |
| `suite_08c9c18ebc224a399ca9580050039ad4` | whatweb, wafw00f, gobuster | planner repeated gobuster to follow its own IDOR plan; cancelled |
| `suite_026437731c2945f2aa585d6d67a86320` | nmap, whatweb, wafw00f | planner repeated nmap/whatweb to probe the interceptor port; cancelled |
| `suite_74c81a82c1c241be8f49bf1b620e5dac` | whatweb, wafw00f | completed; Judge said pass but listed gaps for the broad Case wording, which ABB rejects |
| `suite_d61abc9a27044c3ab29090c721706244`, `suite_e527081769e74486a519eb0bf3afe941` | whatweb, wafw00f | completed; evidence 120,304 and 122,926 characters, over the 120,000 default; Judge inconclusive |
| **`suite_6326c6a622134a4b8a44cfefcba14dd6`** | whatweb, wafw00f | **completed; Judge pass (high); quality gate PASSED** |

## Accepted run

Head `54cefaed6`, Case `watchtower-loopback-fixture-fingerprint`, attempt
`a23c165e853b4ce395e6f311f83ff5d9`, run `8acfdfbf699d43cba0cb05af0fb02879`.
`--timeout 360`, `ABB_LOCAL_JUDGE_MAX_CHARS=200000`, Judge `deepseek-chat`.

- Native graph: planner → worker (whatweb and wafw00f, 3.8 s) → analyst →
  planner `finish`, 8.1 s in total, with three model calls. Container
  execution took 20.5 s.
- whatweb: `200 OK`, `HTTPServer[SimpleHTTP/0.6 Python/3.11.18]`,
  `Title[Watchtower local fixture]`. wafw00f v2.4.2: "No WAF detected by the
  generic detection" after 7 requests. The analyst reported no findings, and
  `is_finished` is `true`.
- Evidence: execution `succeeded`, "SDK execution and evidence validated",
  OTel `complete` with 0 unfinished spans (18 spans). The only egress was 3
  model requests to `api.deepseek.com`, each with status 200.
- Judge: **pass, high confidence**, no issues, no evidence gaps. The evidence
  was 128,467 characters (about 45k tokens).

## Limits

- This shows a normal scan completing through the native loop with real
  scanners. It does not cover the full arsenal. With nmap or gobuster enabled,
  the native planner did not converge in this environment, for causes 2 and 3
  above.
- The agent model is DeepSeek `deepseek-chat`, not the default. The Judge
  limit was raised from 120,000 to 200,000 characters, because a two-round
  trace with its output already slightly exceeds the default.
- The registry entry stays `enabled = false`, `status = "adapting"`. Credited
  KUMA acceptance still waits for the #365 approval.
