"""Render collected benchmark data as a self-contained English HTML report."""

from __future__ import annotations

import html
import json
from typing import Any, Iterable


FAILURE_LABELS = {
    "judge_service": "Remote Judge service failure",
    "integration_http_414": "Agent integration: HTTP 414",
    "integration_runtime": "Agent integration: runtime error",
    "judge_insufficient_evidence": "Insufficient Judge evidence",
    "external_auth": "External credential authentication failure",
    "bba_trace_mapping": "BBA trace mapping defect",
    "user_cancelled": "User cancelled",
    "other": "Other",
    "none": "None",
}
RUN_LABELS = {
    "complete": "Complete",
    "partial": "Partially complete",
    "failed": "Failed",
    "preparation_failed": "Preparation failed",
}


def e(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def pct(value: float | None, digits: int = 1) -> str:
    return "—" if value is None else f"{value * 100:.{digits}f}%"


def num(value: float | None, digits: int = 2) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def integer(value: Any) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return e(value if value is not None else "—")


def raw_link(path: str | None, label: str | None = None) -> str:
    if not path:
        return ""
    # The generated report lives at results/analysis/.
    return f'<a class="raw" href="../../{e(path)}">{e(label or path)}</a>'


def badge(text: Any, tone: str = "neutral") -> str:
    return f'<span class="badge {e(tone)}">{e(text)}</span>'


def json_block(value: Any, *, limit: int = 20_000) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=2)
    truncated = len(text) > limit
    if truncated:
        text = text[:limit] + "\n… [truncated in HTML; open the original artifact]"
    return f'<pre class="json">{e(text)}</pre>'


def table(headers: Iterable[str], rows: Iterable[Iterable[Any]], classes: str = "") -> str:
    head = "".join(f"<th>{e(item)}</th>" for item in headers)
    body = "".join("<tr>" + "".join(f"<td>{item}</td>" for item in row) + "</tr>" for row in rows)
    return f'<div class="table-wrap"><table class="{e(classes)}"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _failure_table(data: dict[str, Any]) -> str:
    counts = data["summary"]["failure_counts"]
    total = data["summary"]["failed"]
    order = [
        "judge_service",
        "integration_http_414",
        "integration_runtime",
        "judge_insufficient_evidence",
        "external_auth",
        "bba_trace_mapping",
        "user_cancelled",
        "other",
    ]
    rows = []
    for key in order:
        count = counts.get(key, 0)
        if count:
            rows.append((e(FAILURE_LABELS[key]), f"<strong>{count}</strong>", pct(count / total)))
    return table(("Exclusive primary cause", "Count", f"Share of {total} failures"), rows)


def _casegen_table(data: dict[str, Any]) -> str:
    rows = [
        (
            e(item.get("suite_id")),
            e(item.get("agent_id")),
            e("Batch" if item.get("case_index") is None else int(item["case_index"]) + 1),
            e(item.get("reason")),
            raw_link(item.get("artifact_directory"), "artifact"),
        )
        for item in data["casegen_failures"]
    ]
    if not rows:
        return '<p class="muted">No CaseGen service failures.</p>'
    return table(("Suite", "Agent", "Planned Case", "Reason", "Raw directory"), rows)


def _agent_table(data: dict[str, Any]) -> str:
    rows = []
    for item in data["per_agent"]:
        judge = item["judge"]
        rows.append(
            (
                e(item["agent_id"]),
                str(item["attempts"]),
                str(item["unique_cases"]),
                f'<strong>{item["healthy"]}</strong>',
                pct(item["rate"]),
                f'{pct(item["wilson_low"])}–{pct(item["wilson_high"])}',
                f'issue {judge.get("issue", 0)} · pass {judge.get("pass", 0)} · insufficient {judge.get("insufficient_evidence", 0)} · missing {judge.get("missing", 0)}',
            )
        )
    return table(("Agent", "Attempts", "Unique Cases", "Strictly healthy", "Healthy rate", "Wilson 95% CI", "Raw Judge status"), rows)


def _run_table(data: dict[str, Any]) -> str:
    rows = []
    for run in data["runs"]:
        tone = "good" if run["status"] == "complete" else "bad" if run["status"] in {"failed", "preparation_failed"} else "warn"
        rows.append(
            (
                str(run["index"]),
                e(run["suite_id"]),
                e(", ".join(run["agents"])),
                e(json.dumps(run["selected_case_counts"], ensure_ascii=False)),
                str(run["generated"]),
                str(run["attempted"]),
                str(run["healthy"]),
                badge(RUN_LABELS[run["status"]], tone),
                badge("Yes", "good") if run["qualifying"] else "",
                raw_link(run.get("artifact"), "events"),
            )
        )
    return table(("#", "Suite", "Agents", "Planned", "Generated", "Executed", "Strictly healthy", "Run result", "Qualifying suite", "Events"), rows)


def _native_table(data: dict[str, Any]) -> str:
    rows = []
    for item in data["native_observations"]:
        tone = "good" if item.get("status") == "succeeded" else "bad"
        rows.append(
            (
                e(item.get("agent_id")),
                badge(item.get("status"), tone),
                e(item.get("error") or "—"),
                e(json.dumps(item.get("tool_statuses", {}), ensure_ascii=False)),
                raw_link(item.get("artifact_directory"), "observe"),
            )
        )
    return table(("Agent", "Status", "Diagnosis", "Tool HTTP", "Artifact"), rows)


def _stats_tables(data: dict[str, Any]) -> str:
    turn_rows = [
        (str(item["turns"]), str(item["attempts"]), str(item["healthy"]), pct(item["rate"]))
        for item in data["by_turns"]
    ]
    period_rows = [
        (e(item["period"]), str(item["attempts"]), str(item["healthy"]), pct(item["rate"]))
        for item in data["by_period"]
    ]
    duration_rows = [
        (
            e(item["agent_id"]),
            str(item["n"]),
            num(item["median_seconds"]),
            num(item["mean_seconds"]),
            num(item["p90_seconds"]),
            num(item["max_seconds"]),
        )
        for item in data["duration_by_agent"]
    ]
    first = data["summary"]["first_seen"]
    reused = data["summary"]["reused"]
    reuse_rows = [
        ("First appearance of Case", str(first["attempts"]), str(first["healthy"]), pct(first["healthy"] / first["attempts"] if first["attempts"] else None)),
        ("Reused Case", str(reused["attempts"]), str(reused["healthy"]), pct(reused["healthy"] / reused["attempts"] if reused["attempts"] else None)),
    ]
    return f"""
    <div class="grid three">
      <section class="panel"><h3>By conversation turns</h3>{table(("Inputs", "Attempts", "Healthy", "Healthy rate"), turn_rows)}</section>
      <section class="panel"><h3>By test period</h3>{table(("Period", "Attempts", "Healthy", "Healthy rate"), period_rows)}</section>
      <section class="panel"><h3>Case reuse</h3>{table(("Type", "Attempts", "Healthy", "Healthy rate"), reuse_rows)}</section>
    </div>
    <section class="panel"><h3>Agent execution time per Input (seconds)</h3>
      {table(("Agent", "Complete intervals n", "Median", "Mean", "P90", "Maximum"), duration_rows)}
    </section>
    <p class="callout warn">These are descriptive statistics. Agent type, Case difficulty, code fixes, and test timing are confounded, so differences cannot be interpreted as a causal Agent performance ranking. Most Case reuse occurred after fixes, which also introduces selection bias.</p>
    """


def _input_detail(item: dict[str, Any], index: int) -> str:
    framework = item["framework"]
    otel = item["otel"]
    trace_rows = [
        (
            e(span.get("name")), e(span.get("kind")), e(span.get("status")),
            num(span.get("duration_ms"), 1), e(span.get("output_preview")),
        )
        for span in framework["spans"]
    ]
    otel_rows = [
        (
            e(span.get("name")), e(span.get("kind")), e(span.get("status")),
            num(span.get("duration_ms"), 1), e(span.get("trace_id")), e(span.get("span_id")),
        )
        for span in otel["spans"]
    ]
    raw = " · ".join(raw_link(path, name) for name, path in item["raw_files"].items())
    result_status = item.get("result", {}).get("status", "missing")
    tone = "good" if result_status == "succeeded" else "bad"
    return f"""
    <details class="input-detail">
      <summary>Input {index} {badge(result_status, tone)} · framework {framework['span_count']} spans · OTEL {otel['span_count']} spans</summary>
      <div class="detail-body">
        <p class="raw-links">{raw}</p>
        <div class="grid two">
          <div><h5>KUMA Input</h5>{json_block(item['input'])}</div>
          <div><h5>Request / mapped input sent to the Agent</h5>{json_block({'request': item['request'], 'mapped_input': item['mapped_input'], 'context': item['context']})}</div>
        </div>
        <h5>External Agent output</h5>{json_block(item['result'])}
        <h5>Result and capture status submitted to the Judge</h5>{json_block(item['submission'])}
        <h5>Internal Agent framework trace</h5>
        <p class="muted">{framework['event_count']} events; execution {num(framework['duration_ms'], 1)} ms; kinds {e(json.dumps(framework['span_kinds'], ensure_ascii=False))}. The table shows up to 80 spans ordered by duration.</p>
        {table(("Span", "Kind", "Status", "ms", "Output preview"), trace_rows) if trace_rows else '<p class="muted">No framework spans.</p>'}
        <h5>OTEL</h5>
        <p class="muted">Status: {e(json.dumps(otel['status'], ensure_ascii=False))}. The table shows up to 80 spans ordered by duration.</p>
        {table(("Span", "Kind", "Status", "ms", "Trace ID", "Span ID"), otel_rows) if otel_rows else '<p class="muted">No OTEL spans.</p>'}
      </div>
    </details>
    """


def _judge_detail(report: dict[str, Any] | None) -> str:
    if not isinstance(report, dict):
        return '<p class="callout bad">No valid Judge report.json. Use the failure category, manifest, and raw artifact to investigate.</p>'
    issues = report.get("issues", [])
    gaps = report.get("evidence_gaps", [])
    issue_rows = [
        (e(item.get("issue_id")), badge(item.get("severity"), "bad" if item.get("severity") == "high" else "warn"), e(item.get("message")))
        for item in issues
    ]
    return f"""
      <p>{badge(report.get('status'), 'good' if report.get('status') == 'pass' else 'warn')} confidence={e(report.get('confidence'))} · stop={e(report.get('stop_reason'))}</p>
      {table(("Issue", "Severity", "Judge message"), issue_rows) if issue_rows else '<p class="muted">The Judge listed no issues.</p>'}
      <h5>Evidence gaps</h5>{json_block(gaps)}
      <details><summary>Complete Judge JSON</summary>{json_block(report)}</details>
    """


def _case_card(case: dict[str, Any]) -> str:
    healthy = bool(case["healthy"])
    judge = case.get("judge_status") or "missing"
    status_tone = "good" if healthy else "bad"
    judge_tone = "good" if judge == "pass" else "warn" if judge in {"issue", "insufficient_evidence"} else "bad"
    flags = case.get("review_flags", [])
    scope = case.get("scope_review")
    annotations = ""
    if flags or scope:
        rows = [(e(item.get("type")), e(item.get("detail"))) for item in flags]
        if scope:
            rows.append((f"scope:{e(scope.get('scope_review'))}", e(scope.get("reason"))))
        annotations = f'<h4>Manual review flags</h4>{table(("Type", "Description"), rows)}'
    secondary = "".join(f"<li>{e(item)}</li>" for item in case.get("secondary_failures", []))
    network = case.get("network", {})
    endpoint_rows = [
        (e(row.get("event")), e(row.get("host")), e(row.get("method")), e(row.get("status")), str(row.get("count")))
        for row in network.get("endpoints", [])
    ]
    inputs = "".join(_input_detail(item, index) for index, item in enumerate(case["inputs"], 1))
    raw = " · ".join(raw_link(path, name) for name, path in case.get("raw_files", {}).items())
    filters = ["healthy" if healthy else "failed", str(judge), str(case.get("agent_id")), str(case.get("failure_category"))]
    search = " ".join(str(case.get(k, "")) for k in ("agent_id", "case_id", "suite_id", "title", "description", "failure_label"))
    return f"""
    <article class="case-card" data-filter="{e(' '.join(filters))}" data-search="{e(search.lower())}">
      <details>
        <summary>
          <span class="case-number">#{case['run_index']}.{(case.get('case_index') or 0) + 1}</span>
          <span class="case-title">{e(case['title'])}</span>
          {badge(case.get('agent_id'), 'neutral')} {badge('Healthy' if healthy else 'Failed', status_tone)} {badge(judge, judge_tone)}
          <span class="case-meta">{len(case['inputs'])} inputs · attempt {case['attempt_number']}</span>
        </summary>
        <div class="case-body">
          <p class="ids"><code>{e(case.get('case_id'))}</code><br><code>{e(case.get('suite_id'))}</code></p>
          <p>{e(case.get('description'))}</p>
          <div class="classification">
            <strong>Primary classification:</strong> {e(FAILURE_LABELS.get(case['failure_category'], case['failure_category']))} — {e(case['failure_label'])}
            {f'<ul>{secondary}</ul>' if secondary else ''}
          </div>
          <p class="raw-links">{raw}</p>
          {annotations}
          <h4>CaseGen artifact</h4>{json_block(case['case'])}
          <h4>Input, Agent trace, output, and OTEL for each turn</h4>{inputs or '<p class="muted">This attempt has no saved Input artifacts.</p>'}
          <h4>Network summary</h4>
          <p class="muted">{network.get('event_count', 0)} interceptor events; event kinds {e(json.dumps(network.get('events', {}), ensure_ascii=False))}. HTTP bodies are not embedded in the report to control size and reduce exposure of sensitive information.</p>
          {table(("Event", "Host", "Method", "Status", "Count"), endpoint_rows) if endpoint_rows else '<p class="muted">No response endpoint records.</p>'}
          <h4>Judge</h4>{_judge_detail(case.get('judge_report'))}
        </div>
      </details>
    </article>
    """


def _case_explorer(data: dict[str, Any]) -> str:
    cards = "".join(_case_card(case) for case in data["cases"])
    return f"""
    <section id="cases" class="section">
      <div class="section-head"><div><p class="eyebrow">RAW EVIDENCE</p><h2>{len(data['cases'])} Case attempts</h2></div><p>Collapsed by default. Filter by pipeline status, Judge status, Agent, or failure cause.</p></div>
      <div class="toolbar">
        <input id="search" type="search" placeholder="Search Agent, Case ID, Suite, title, or error…">
        <div id="filters">
          <button class="active" data-value="all">All {len(data['cases'])}</button>
          <button data-value="healthy">Strictly healthy</button><button data-value="failed">Failed</button>
          <button data-value="issue">Judge issue</button><button data-value="pass">Judge pass</button>
          <button data-value="insufficient_evidence">Insufficient evidence</button><button data-value="judge_service">Judge service failure</button>
          <button data-value="react-agent">ReAct</button><button data-value="trading-agents">Trading</button><button data-value="gpt-researcher">GPT Researcher</button>
        </div>
        <span id="visible-count"></span>
      </div>
      <div id="case-list">{cards}</div>
    </section>
    """


def render_report(data: dict[str, Any]) -> str:
    s = data["summary"]
    live = data.get("live_3x5", {})
    live_counts = live.get("counts", {}) if isinstance(live, dict) else {}
    usage = data.get("usage", {})
    run_counts = s["run_statuses"]
    judge_counts = s["judge_counts"]
    healthy_judge = s["healthy_judge_counts"]
    judge_service_codes = ", ".join(
        f"{name} {count}" for name, count in sorted(s["judge_service_codes"].items())
    )
    trace_reasons = s["trace_reasons"]
    sources = "".join(f"<li>{raw_link(path)}</li>" for path in data["source_documents"])
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(data['meta']['title'])}</title>
<style>
:root{{--ink:#18211c;--muted:#68736d;--paper:#f5f2e9;--card:#fffef9;--line:#d7d2c4;--green:#136f4a;--green-bg:#dff3e8;--red:#9e332c;--red-bg:#f9e5e1;--amber:#8b5a0b;--amber-bg:#f8edcc;--blue:#315c78;--shadow:0 12px 32px rgba(34,39,35,.08)}}
*{{box-sizing:border-box}} html{{scroll-behavior:smooth}} body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.58 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}} a{{color:var(--blue)}} code,pre{{font-family:"SFMono-Regular",Consolas,monospace}} .wrap{{max-width:1500px;margin:auto;padding:48px 28px 120px}} .hero{{border-top:8px solid var(--ink);padding:34px 0 28px;display:grid;grid-template-columns:1.4fr 1fr;gap:40px}} .eyebrow{{font:700 12px/1.2 monospace;letter-spacing:.16em;color:var(--green);margin:0 0 8px}} h1{{font:700 clamp(40px,6vw,82px)/.98 Georgia,serif;letter-spacing:-.045em;margin:0 0 22px}} h2{{font:700 34px/1.1 Georgia,serif;margin:0}} h3{{font-size:20px;margin:0 0 12px}} h4{{font-size:17px;margin:28px 0 10px}} h5{{font-size:14px;margin:22px 0 8px}} .lede{{font-size:19px;max-width:750px}} .meta{{align-self:end;border-left:1px solid var(--line);padding-left:28px}} .section{{padding:54px 0;border-top:1px solid var(--line)}} .section-head{{display:flex;justify-content:space-between;gap:30px;align-items:end;margin-bottom:24px}} .section-head>p{{max-width:580px;color:var(--muted)}} .cards{{display:grid;grid-template-columns:repeat(5,1fr);gap:12px}} .metric{{background:var(--card);padding:20px;border:1px solid var(--line);box-shadow:var(--shadow)}} .metric strong{{display:block;font:700 36px/1 Georgia,serif;margin-bottom:8px}} .metric span{{color:var(--muted)}} .grid{{display:grid;gap:16px}} .grid.two{{grid-template-columns:repeat(2,minmax(0,1fr))}} .grid.three{{grid-template-columns:repeat(3,minmax(0,1fr))}} .panel{{background:var(--card);border:1px solid var(--line);padding:22px;margin-bottom:16px}} .callout{{padding:16px 18px;border-left:4px solid var(--blue);background:#e8f0f3}} .callout.warn{{background:var(--amber-bg);border-color:var(--amber)}} .callout.bad{{background:var(--red-bg);border-color:var(--red)}} .muted{{color:var(--muted)}} .table-wrap{{overflow:auto;border:1px solid var(--line);background:var(--card)}} table{{width:100%;border-collapse:collapse;font-size:13px}} th{{text-align:left;background:#ebe7dc;position:sticky;top:0;z-index:1}} th,td{{padding:10px 12px;border-bottom:1px solid var(--line);vertical-align:top}} tr:last-child td{{border-bottom:0}} .badge{{display:inline-block;padding:2px 8px;border-radius:999px;background:#ecebe6;color:#4f5753;font-size:11px;font-weight:700;white-space:nowrap}} .badge.good{{background:var(--green-bg);color:var(--green)}} .badge.bad{{background:var(--red-bg);color:var(--red)}} .badge.warn{{background:var(--amber-bg);color:var(--amber)}} .raw{{font:12px monospace}} .toolbar{{position:sticky;top:0;z-index:10;background:rgba(245,242,233,.96);backdrop-filter:blur(10px);padding:14px 0;border-bottom:1px solid var(--line);margin-bottom:18px}} .toolbar input{{width:100%;padding:12px 14px;border:1px solid var(--line);background:white;font-size:15px;margin-bottom:10px}} #filters{{display:flex;flex-wrap:wrap;gap:7px}} button{{border:1px solid var(--line);background:var(--card);padding:7px 11px;border-radius:4px;cursor:pointer}} button.active{{background:var(--ink);color:white;border-color:var(--ink)}} #visible-count{{display:block;color:var(--muted);margin-top:8px}} .case-card{{background:var(--card);border:1px solid var(--line);margin:10px 0;box-shadow:0 4px 12px rgba(34,39,35,.035)}} .case-card>details>summary{{display:flex;gap:9px;align-items:center;padding:15px 18px;cursor:pointer;list-style:none}} .case-card>details>summary::-webkit-details-marker{{display:none}} .case-card>details>summary::before{{content:"＋";font:700 17px monospace}} .case-card>details[open]>summary::before{{content:"−"}} .case-title{{font-weight:700;flex:1}} .case-number,.case-meta{{font:12px monospace;color:var(--muted)}} .case-body{{padding:0 22px 28px;border-top:1px solid var(--line)}} .ids{{color:var(--muted)}} .classification{{padding:12px 14px;background:#f0eee7}} .raw-links{{overflow-wrap:anywhere}} details.input-detail{{border:1px solid var(--line);margin:10px 0;background:#faf9f4}} details.input-detail>summary{{padding:12px;cursor:pointer;font-weight:700}} .detail-body{{padding:0 14px 18px}} pre.json{{white-space:pre-wrap;overflow-wrap:anywhere;max-height:520px;overflow:auto;background:#1e2521;color:#dce8df;padding:14px;font-size:12px;line-height:1.5}} .decision{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;counter-reset:step}} .decision>div{{padding:16px;background:var(--card);border:1px solid var(--line)}} .decision>div::before{{counter-increment:step;content:counter(step);display:block;width:26px;height:26px;line-height:26px;text-align:center;border-radius:50%;background:var(--ink);color:white;margin-bottom:10px}} footer{{border-top:1px solid var(--line);padding-top:30px;color:var(--muted)}}
@media(max-width:980px){{.hero,.grid.two,.grid.three{{grid-template-columns:1fr}}.cards{{grid-template-columns:repeat(2,1fr)}}.decision{{grid-template-columns:1fr 1fr}}.section-head{{display:block}}.case-card>details>summary{{flex-wrap:wrap}}}} @media(max-width:560px){{.wrap{{padding:28px 14px 80px}}.cards,.decision{{grid-template-columns:1fr}}}}
@media print{{.toolbar{{position:static}}.case-card{{break-inside:avoid}}}}
</style>
</head>
<body><main class="wrap">
<header class="hero"><div><p class="eyebrow">BBA / BENCHMARK FORENSICS / {e(data['meta']['date'])}</p><h1>How did today's tests actually perform?</h1><p class="lede">Starting from {s['runs']} Runs, {s['attempts']} real Case attempts, and {s['input_artifacts']} saved Input artifacts, this report separates three questions: whether the system completed end to end, whether the Judge returned a report, and whether that report identified an Agent issue.</p></div><div class="meta"><strong>Report generated</strong><br>{e(data['meta']['generated_at'])}<br><br><strong>Campaign</strong><br>{e(data['meta']['campaign_status'])} · {e(data['meta']['campaign_stop_reason'])}<br><br><strong>Data source</strong><br>{raw_link(data['meta']['ledger'])}</div></header>

<section class="section"><div class="cards">
  <div class="metric"><strong>{s['attempts']}</strong><span>Real Case attempts</span></div>
  <div class="metric"><strong>{s['healthy']}</strong><span>Strictly healthy pipeline · {pct(s['healthy_rate'])}</span></div>
  <div class="metric"><strong>{s['failed']}</strong><span>Not strictly healthy</span></div>
  <div class="metric"><strong>{s['judge_reports']}</strong><span>Valid Judge reports</span></div>
  <div class="metric"><strong>{s['unique_cases']}</strong><span>Unique Cases · {s['reused_attempts']} reused attempts</span></div>
</div></section>

<section class="section"><div class="section-head"><div><p class="eyebrow">DEFINITIONS</p><h2>Define “healthy” first</h2></div><p>This report uses the campaign ledger's strict acceptance result: Agent execution, OTEL, submission, evidence, Judge, host trace validation, and cleanup must all complete. The Judge's behavioral verdict is counted separately.</p></div>
<div class="decision"><div><strong>CaseGen</strong><br>Produced a saved, executable Case.</div><div><strong>Agent + trace</strong><br>Completed each input and saved Agent output, framework trace, and OTEL.</div><div><strong>Judge</strong><br>Returned a structured report.json; `issue` is still a valid report.</div><div><strong>Host acceptance</strong><br>Trace validation, cleanup, and all other checks passed.</div></div>
<p class="callout"><strong>Key distinction:</strong> among {s['healthy']} strictly healthy attempts, the Judge returned {healthy_judge.get('issue',0)} `issue` verdicts and {healthy_judge.get('pass',0)} `pass` verdicts. An `issue` means the evaluation infrastructure successfully produced a behavioral finding; it is not a system failure. Attribution may still involve Agent behavior, Case/capability mismatch, the integration layer, Judge interpretation, or a mixture.</p>
</section>

<section class="section"><div class="section-head"><div><p class="eyebrow">FAILURES</p><h2>{s['failed']} unsuccessful attempts: primary causes</h2></div><p>Primary causes are mutually exclusive and sum to {s['failed']}, which keeps percentages meaningful. Each Case still retains secondary causes, such as a Judge service failure accompanied by an Agent HTTP 414.</p></div>
<div class="grid two"><section class="panel"><h3>Case attempt failures</h3>{_failure_table(data)}</section><section class="panel"><h3>Generation and preparation</h3><p><strong>{s['casegen_service_failures']}</strong> remote CaseGen service failures produced no attempt; <strong>{s['preparation_failures']}</strong> Agent Profiles failed local validation before CaseGen was called.</p><p class="muted">Batch generation errors also produced {s['casegen_skipped_slots']} CaseSkipped placeholders. They are consequences of the failures and are not counted again as CaseGen root causes. CaseGen failures are kept outside the denominator of the subsequent 160 attempts.</p></section></div>
<h3>CaseGen service failures</h3>{_casegen_table(data)}
</section>

<section class="section"><div class="section-head"><div><p class="eyebrow">JUDGE</p><h2>Judge results, failures, and attribution</h2></div><p>{s['requests'].get('judge_posts',0)} Judge POST requests produced {s['judge_reports']} structured reports; the remaining {s['attempts']-s['judge_reports']} attempts have no valid report.</p></div>
<div class="grid three">
<section class="panel"><h3>Report status</h3><p>issue <strong>{judge_counts.get('issue',0)}</strong><br>pass <strong>{judge_counts.get('pass',0)}</strong><br>insufficient_evidence <strong>{judge_counts.get('insufficient_evidence',0)}</strong><br>missing <strong>{judge_counts.get('missing',0)}</strong></p></section>
<section class="panel"><h3>{s['attempts']-s['judge_reports']} attempts without a valid report</h3><p><strong>{sum(s['judge_service_codes'].values())}</strong> remote Judge operation failures: {e(judge_service_codes)}.</p><p><strong>{s['attempts']-s['judge_reports']-sum(s['judge_service_codes'].values())}</strong> attempts ended before the Judge returned a valid report.</p></section>
<section class="panel"><h3>Judge issues</h3><p>{sum(s['judge_issue_severities'].values())} total: high {s['judge_issue_severities'].get('high',0)}, medium {s['judge_issue_severities'].get('medium',0)}, low {s['judge_issue_severities'].get('low',0)}.</p><p>{s['judge_reports']-s['reports_with_evidence_gaps']} / {s['judge_reports']} reports have empty evidence_gaps; {judge_counts.get('insufficient_evidence',0)} insufficient_evidence reports provide no more specific cause.</p></section>
</div>
<p class="callout warn"><strong>Distinguishing BBA defects from normal issues:</strong> when the pipeline is strictly healthy and has a report, preserve a Judge `issue` as a normal evaluation result, then review the Case scope, native Agent capability, entrypoint semantics, and Judge text for attribution. When execution, trace, Judge service, or host validation fails, classify the result as an infrastructure or integration problem first and exclude it from clean Agent capability statistics. Case details include manual review flags without changing the official Judge result.</p>
</section>

<section class="section"><div class="section-head"><div><p class="eyebrow">AGENTS</p><h2>Results by Agent</h2></div><p>Wilson intervals express small-sample uncertainty better than raw percentages. The three Case groups and test phases differ, so do not interpret this as a fair cross-Agent ranking.</p></div>{_agent_table(data)}</section>

<section class="section"><div class="section-head"><div><p class="eyebrow">DESCRIPTIVE STATISTICS</p><h2>Useful statistics with clear limits</h2></div></div>{_stats_tables(data)}</section>

<section class="section"><div class="section-head"><div><p class="eyebrow">TRACE & OTEL</p><h2>Observability across {s['input_artifacts']} Input turns</h2></div><p>Expand each Case to inspect its input, mapped request, Agent output, framework trace, OTEL spans, submission, and Judge report.</p></div>
<div class="cards">
<div class="metric"><strong>{s['input_artifacts']}</strong><span>Saved Input artifacts</span></div><div class="metric"><strong>{s['input_statuses'].get('succeeded',0)}</strong><span>Successful Agent Inputs</span></div><div class="metric"><strong>{s['otel_spans']:,}</strong><span>OTEL spans</span></div><div class="metric"><strong>{s['framework_spans']:,}</strong><span>framework spans</span></div><div class="metric"><strong>{s['otel_statuses'].get('complete',0)}</strong><span>Complete OTEL captures</span></div>
</div>
<p class="callout warn">Of {s['submitted_steps']} submitted steps, {s['trace_partial_steps']} trace captures are `partial`: {e(json.dumps(trace_reasons, ensure_ascii=False))}. The main cause is the SDK allowlist dropping some attributes. This is a trace-fidelity warning, not a Case failure. Strictly healthy Judge reports have no evidence gaps.</p>
</section>

<section class="section"><div class="section-head"><div><p class="eyebrow">INTEGRATION</p><h2>Native integration diagnostics before the benchmark</h2></div><p>These {len(data['native_observations'])} observations are not part of the {s['attempts']} Case attempts. They help locate network declaration, third-party rate-limit, and trace acceptance problems.</p></div>{_native_table(data)}</section>

<section class="section"><div class="section-head"><div><p class="eyebrow">REFERENCE SUITE</p><h2>The most complete 3 Agents × 5 Cases suite</h2></div><p>{e(live.get('suite_id'))}</p></div>
<div class="cards"><div class="metric"><strong>{live_counts.get('executed_cases','—')}</strong><span>Cases completed execution</span></div><div class="metric"><strong>{live_counts.get('actual_inputs','—')}</strong><span>Inputs</span></div><div class="metric"><strong>{live_counts.get('judge_reports','—')}</strong><span>Judge reports</span></div><div class="metric"><strong>{live.get('concurrency',{}).get('observed_case_lifecycle_peak','—')}</strong><span>Observed peak concurrency</span></div><div class="metric"><strong>{num(live.get('total_elapsed_seconds'),1)}s</strong><span>Suite wall time</span></div></div>
<p class="callout">This suite had no CaseGen, Agent execution, Judge service, host validation, or cleanup failures. The Judge returned 13 issue, 1 insufficient_evidence, and 1 pass verdict. Under this report's strict definition, the one insufficient-evidence attempt is excluded from the 128 healthy attempts, so this suite is 14/15 strictly healthy. The earlier audit's “15 executions completed” used a broader execution-only definition.</p>
</section>

<section class="section"><div class="section-head"><div><p class="eyebrow">COST</p><h2>Observed model usage</h2></div></div>
<div class="grid two"><section class="panel"><h3>OpenRouter</h3><p><strong>{integer(usage.get('openrouter_responses'))}</strong> responses<br><strong>{integer(usage.get('reported_total_tokens'))}</strong> tokens<br><strong>${e(usage.get('reported_cost_usd','—'))}</strong> provider-reported subtotal</p></section><section class="panel"><h3>KUMA</h3><p>CaseGen/Judge token usage and costs are not exposed in local artifacts, so the OpenRouter subtotal cannot be presented as the total campaign cost.</p><p class="muted">Another {usage.get('responses_without_cost','—')} OpenRouter responses have no cost field.</p></section></div>
</section>

<section class="section"><div class="section-head"><div><p class="eyebrow">RUN LEDGER</p><h2>Completion status for {s['runs']} Runs</h2></div><p>{run_counts.get('complete',0)} complete, {run_counts.get('partial',0)} partially complete, {run_counts.get('failed',0)} failed, and {run_counts.get('preparation_failed',0)} preparation failures. A complete Run requires every planned Case to be strictly healthy.</p></div>{_run_table(data)}</section>

{_case_explorer(data)}

<footer><h3>Sources and limitations</h3><ul>{sources}</ul><p>The report recursively redacts fields such as API key, Authorization, Cookie, token, and password. Network response bodies are not embedded in the HTML. Raw artifact links point into the local repository; keep the HTML under results/analysis/ when moving it.</p></footer>
</main>
<script>
const cards=[...document.querySelectorAll('.case-card')]; const search=document.getElementById('search'); const buttons=[...document.querySelectorAll('#filters button')]; const count=document.getElementById('visible-count'); let filter='all';
function apply(){{const q=search.value.trim().toLowerCase();let n=0;cards.forEach(card=>{{const okFilter=filter==='all'||card.dataset.filter.split(' ').includes(filter);const okSearch=!q||card.dataset.search.includes(q);const show=okFilter&&okSearch;card.hidden=!show;if(show)n++;}});count.textContent=`Showing ${{n}} / ${{cards.length}} attempts`;}}
buttons.forEach(button=>button.addEventListener('click',()=>{{buttons.forEach(b=>b.classList.remove('active'));button.classList.add('active');filter=button.dataset.value;apply();}}));search.addEventListener('input',apply);apply();
</script></body></html>"""
