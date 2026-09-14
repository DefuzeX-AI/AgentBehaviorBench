"""Render collected benchmark data as a self-contained Chinese HTML report."""

from __future__ import annotations

import html
import json
from typing import Any, Iterable


FAILURE_LABELS = {
    "judge_service": "远程 Judge 服务失败",
    "integration_http_414": "Agent 接入：HTTP 414",
    "integration_runtime": "Agent 接入：运行时错误",
    "judge_insufficient_evidence": "Judge 证据不足",
    "external_auth": "外部凭证认证失败",
    "bba_trace_mapping": "BBA trace 映射缺陷",
    "user_cancelled": "用户取消",
    "other": "其他",
    "none": "无",
}
RUN_LABELS = {
    "complete": "完整跑通",
    "partial": "部分跑通",
    "failed": "全部失败",
    "preparation_failed": "准备阶段失败",
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
        text = text[:limit] + "\n… [HTML 中已截断；请打开原始 artifact]"
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
    return table(("互斥主因", "次数", f"占 {total} 次失败"), rows)


def _casegen_table(data: dict[str, Any]) -> str:
    rows = [
        (
            e(item.get("suite_id")),
            e(item.get("agent_id")),
            e("批次" if item.get("case_index") is None else int(item["case_index"]) + 1),
            e(item.get("reason")),
            raw_link(item.get("artifact_directory"), "artifact"),
        )
        for item in data["casegen_failures"]
    ]
    if not rows:
        return '<p class="muted">没有 CaseGen 服务失败。</p>'
    return table(("Suite", "Agent", "计划 Case", "原因", "原始目录"), rows)


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
    return table(("Agent", "Attempts", "唯一 Case", "严格跑通", "跑通率", "Wilson 95% CI", "Judge 原始状态"), rows)


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
                badge("是", "good") if run["qualifying"] else "",
                raw_link(run.get("artifact"), "events"),
            )
        )
    return table(("#", "Suite", "Agents", "计划", "生成", "执行", "严格跑通", "Run 结果", "资格套件", "事件"), rows)


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
    return table(("Agent", "状态", "诊断", "工具 HTTP", "Artifact"), rows)


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
        ("Case 首次出现", str(first["attempts"]), str(first["healthy"]), pct(first["healthy"] / first["attempts"] if first["attempts"] else None)),
        ("复用 Case", str(reused["attempts"]), str(reused["healthy"]), pct(reused["healthy"] / reused["attempts"] if reused["attempts"] else None)),
    ]
    return f"""
    <div class="grid three">
      <section class="panel"><h3>按对话轮数</h3>{table(("Inputs", "Attempts", "跑通", "跑通率"), turn_rows)}</section>
      <section class="panel"><h3>按测试时段</h3>{table(("时段", "Attempts", "跑通", "跑通率"), period_rows)}</section>
      <section class="panel"><h3>Case 复用</h3>{table(("类型", "Attempts", "跑通", "跑通率"), reuse_rows)}</section>
    </div>
    <section class="panel"><h3>Agent 单次 Input 执行时长（秒）</h3>
      {table(("Agent", "完整区间 n", "中位数", "平均", "P90", "最大"), duration_rows)}
    </section>
    <p class="callout warn">这些是描述性统计。Agent 类型、Case 难度、代码修复和测试时间相互混杂，不能把差异解释成 Agent 的因果性能排名。复用 Case 多数发生在修复后，也存在选择偏差。</p>
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
          <div><h5>KUMA 输入</h5>{json_block(item['input'])}</div>
          <div><h5>传给 Agent 的 request / mapped input</h5>{json_block({'request': item['request'], 'mapped_input': item['mapped_input'], 'context': item['context']})}</div>
        </div>
        <h5>Agent 外部输出</h5>{json_block(item['result'])}
        <h5>提交给 Judge 的结果与 capture status</h5>{json_block(item['submission'])}
        <h5>Agent 内部 framework trace</h5>
        <p class="muted">{framework['event_count']} 个事件；执行 {num(framework['duration_ms'], 1)} ms；类型 {e(json.dumps(framework['span_kinds'], ensure_ascii=False))}。表格按时长显示最多 80 个 span。</p>
        {table(("Span", "Kind", "Status", "ms", "输出预览"), trace_rows) if trace_rows else '<p class="muted">没有 framework span。</p>'}
        <h5>OTEL</h5>
        <p class="muted">状态：{e(json.dumps(otel['status'], ensure_ascii=False))}。表格按时长显示最多 80 个 span。</p>
        {table(("Span", "Kind", "Status", "ms", "Trace ID", "Span ID"), otel_rows) if otel_rows else '<p class="muted">没有 OTEL span。</p>'}
      </div>
    </details>
    """


def _judge_detail(report: dict[str, Any] | None) -> str:
    if not isinstance(report, dict):
        return '<p class="callout bad">没有有效 Judge report.json。请结合 failure category、manifest 和原始 artifact 判断。</p>'
    issues = report.get("issues", [])
    gaps = report.get("evidence_gaps", [])
    issue_rows = [
        (e(item.get("issue_id")), badge(item.get("severity"), "bad" if item.get("severity") == "high" else "warn"), e(item.get("message")))
        for item in issues
    ]
    return f"""
      <p>{badge(report.get('status'), 'good' if report.get('status') == 'pass' else 'warn')} confidence={e(report.get('confidence'))} · stop={e(report.get('stop_reason'))}</p>
      {table(("Issue", "Severity", "Judge message"), issue_rows) if issue_rows else '<p class="muted">Judge 没有列出 issue。</p>'}
      <h5>Evidence gaps</h5>{json_block(gaps)}
      <details><summary>完整 Judge JSON</summary>{json_block(report)}</details>
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
        annotations = f'<h4>人工复核标记</h4>{table(("类型", "说明"), rows)}'
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
          {badge(case.get('agent_id'), 'neutral')} {badge('跑通' if healthy else '未跑通', status_tone)} {badge(judge, judge_tone)}
          <span class="case-meta">{len(case['inputs'])} inputs · attempt {case['attempt_number']}</span>
        </summary>
        <div class="case-body">
          <p class="ids"><code>{e(case.get('case_id'))}</code><br><code>{e(case.get('suite_id'))}</code></p>
          <p>{e(case.get('description'))}</p>
          <div class="classification">
            <strong>主分类：</strong>{e(FAILURE_LABELS.get(case['failure_category'], case['failure_category']))} — {e(case['failure_label'])}
            {f'<ul>{secondary}</ul>' if secondary else ''}
          </div>
          <p class="raw-links">{raw}</p>
          {annotations}
          <h4>CaseGen 产物</h4>{json_block(case['case'])}
          <h4>每轮输入、Agent trace、输出和 OTEL</h4>{inputs or '<p class="muted">这个 attempt 没有落盘 Input artifact。</p>'}
          <h4>网络摘要</h4>
          <p class="muted">{network.get('event_count', 0)} 个 interceptor 事件；事件类型 {e(json.dumps(network.get('events', {}), ensure_ascii=False))}。HTTP body 不嵌入报告，避免体积和敏感信息风险。</p>
          {table(("事件", "Host", "Method", "Status", "次数"), endpoint_rows) if endpoint_rows else '<p class="muted">没有 response endpoint 记录。</p>'}
          <h4>Judge</h4>{_judge_detail(case.get('judge_report'))}
        </div>
      </details>
    </article>
    """


def _case_explorer(data: dict[str, Any]) -> str:
    cards = "".join(_case_card(case) for case in data["cases"])
    return f"""
    <section id="cases" class="section">
      <div class="section-head"><div><p class="eyebrow">RAW EVIDENCE</p><h2>{len(data['cases'])} 次 Case attempt</h2></div><p>默认折叠。可按流水线状态、Judge 状态、Agent 或失败原因筛选。</p></div>
      <div class="toolbar">
        <input id="search" type="search" placeholder="搜索 Agent、Case ID、Suite、标题或错误…">
        <div id="filters">
          <button class="active" data-value="all">全部 {len(data['cases'])}</button>
          <button data-value="healthy">严格跑通</button><button data-value="failed">未跑通</button>
          <button data-value="issue">Judge issue</button><button data-value="pass">Judge pass</button>
          <button data-value="insufficient_evidence">证据不足</button><button data-value="judge_service">Judge 服务失败</button>
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
    judge_service_codes = "、".join(
        f"{name} {count}" for name, count in sorted(s["judge_service_codes"].items())
    )
    trace_reasons = s["trace_reasons"]
    sources = "".join(f"<li>{raw_link(path)}</li>" for path in data["source_documents"])
    return f"""<!doctype html>
<html lang="zh-CN">
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
<header class="hero"><div><p class="eyebrow">BBA / BENCHMARK FORENSICS / {e(data['meta']['date'])}</p><h1>今天的测试，究竟跑得怎么样？</h1><p class="lede">从 {s['runs']} 个 Run、{s['attempts']} 次真实 Case attempt、{s['input_artifacts']} 个落盘 Input artifact 出发，把“系统是否完整跑通”“Judge 是否返回报告”“Judge 报告认为 Agent 有问题”拆成三个不同问题。</p></div><div class="meta"><strong>报告生成</strong><br>{e(data['meta']['generated_at'])}<br><br><strong>Campaign</strong><br>{e(data['meta']['campaign_status'])} · {e(data['meta']['campaign_stop_reason'])}<br><br><strong>数据源</strong><br>{raw_link(data['meta']['ledger'])}</div></header>

<section class="section"><div class="cards">
  <div class="metric"><strong>{s['attempts']}</strong><span>真实 Case attempts</span></div>
  <div class="metric"><strong>{s['healthy']}</strong><span>严格流水线跑通 · {pct(s['healthy_rate'])}</span></div>
  <div class="metric"><strong>{s['failed']}</strong><span>未严格跑通</span></div>
  <div class="metric"><strong>{s['judge_reports']}</strong><span>有效 Judge reports</span></div>
  <div class="metric"><strong>{s['unique_cases']}</strong><span>唯一 Case · {s['reused_attempts']} 次复用</span></div>
</div></section>

<section class="section"><div class="section-head"><div><p class="eyebrow">DEFINITIONS</p><h2>先统一“跑通”的口径</h2></div><p>这里使用 campaign ledger 的严格验收结果：Agent 执行、OTEL、submission、evidence、Judge、host trace validation 与 cleanup 必须完成。Judge 的业务结论单独统计。</p></div>
<div class="decision"><div><strong>CaseGen</strong><br>生成了可落盘、可执行的 Case。</div><div><strong>Agent + trace</strong><br>每轮输入完成，Agent 输出、framework trace 与 OTEL 落盘。</div><div><strong>Judge</strong><br>返回结构化 report.json；`issue` 仍是一份有效报告。</div><div><strong>Host 验收</strong><br>trace、cleanup 等全部通过，才记为严格跑通。</div></div>
<p class="callout"><strong>关键区别：</strong>{s['healthy']} 次严格跑通中，Judge 有 {healthy_judge.get('issue',0)} 次 `issue`、{healthy_judge.get('pass',0)} 次 `pass`。这些 `issue` 代表“评测基础设施完整地产生了行为问题报告”，不是系统失败。责任归因还可能是 Agent 行为、Case/能力不匹配、接入层、Judge 误读或混合原因。</p>
</section>

<section class="section"><div class="section-head"><div><p class="eyebrow">FAILURES</p><h2>{s['failed']} 次未跑通：主因统计</h2></div><p>主因互斥，总和等于 {s['failed']}，便于计算比例。Case 上仍保留次因，例如 Judge 服务失败同时伴随 Agent HTTP 414。</p></div>
<div class="grid two"><section class="panel"><h3>Case attempt 失败</h3>{_failure_table(data)}</section><section class="panel"><h3>生成与准备阶段</h3><p><strong>{s['casegen_service_failures']}</strong> 次远程 CaseGen 服务失败，未形成 attempt；<strong>{s['preparation_failures']}</strong> 次 Agent Profile 本地校验失败，尚未调用 CaseGen。</p><p class="muted">批量生成错误还派生出 {s['casegen_skipped_slots']} 个 CaseSkipped 占位结果；它们是失败的后果，不重复计为 CaseGen 根因。CaseGen 失败与后面的 160 attempts 分母分开。</p></section></div>
<h3>CaseGen 服务失败清单</h3>{_casegen_table(data)}
</section>

<section class="section"><div class="section-head"><div><p class="eyebrow">JUDGE</p><h2>Judge：结果、失败与责任归因</h2></div><p>{s['requests'].get('judge_posts',0)} 次 Judge POST 对应 {s['judge_reports']} 份结构化报告；其余 {s['attempts']-s['judge_reports']} 次没有有效报告。</p></div>
<div class="grid three">
<section class="panel"><h3>报告状态</h3><p>issue <strong>{judge_counts.get('issue',0)}</strong><br>pass <strong>{judge_counts.get('pass',0)}</strong><br>insufficient_evidence <strong>{judge_counts.get('insufficient_evidence',0)}</strong><br>missing <strong>{judge_counts.get('missing',0)}</strong></p></section>
<section class="panel"><h3>无有效报告的 {s['attempts']-s['judge_reports']} 次</h3><p><strong>{sum(s['judge_service_codes'].values())}</strong> 次远程 Judge operation 失败：{e(judge_service_codes)}。</p><p><strong>{s['attempts']-s['judge_reports']-sum(s['judge_service_codes'].values())}</strong> 次在 Judge 返回有效报告前结束。</p></section>
<section class="panel"><h3>Judge issues</h3><p>共 {sum(s['judge_issue_severities'].values())} 条：high {s['judge_issue_severities'].get('high',0)}、medium {s['judge_issue_severities'].get('medium',0)}、low {s['judge_issue_severities'].get('low',0)}。</p><p>{s['judge_reports']-s['reports_with_evidence_gaps']} / {s['judge_reports']} 份报告的 evidence_gaps 为空；其中 {judge_counts.get('insufficient_evidence',0)} 份 insufficient_evidence 没有提供更细原因。</p></section>
</div>
<p class="callout warn"><strong>如何分辨 BBA 问题与正常 issue：</strong>若流水线严格跑通且有 report，Judge `issue` 首先作为正常评测结果保存；再用 Case scope、Agent 原生能力、entrypoint 语义和 Judge 文本做人工归因。若 execution/trace/Judge service/host validation 失败，则先归为基础设施或接入问题，并排除出干净的 Agent 能力统计。报告的 Case 详情已附上人工 review flags，但不篡改官方 Judge 结果。</p>
</section>

<section class="section"><div class="section-head"><div><p class="eyebrow">AGENTS</p><h2>按 Agent 查看</h2></div><p>Wilson 区间比简单百分比更能反映小样本不确定性。三组 Case 与测试阶段不同，因此不要横向解释为公平排行榜。</p></div>{_agent_table(data)}</section>

<section class="section"><div class="section-head"><div><p class="eyebrow">DESCRIPTIVE STATISTICS</p><h2>有意义，但有边界的统计</h2></div></div>{_stats_tables(data)}</section>

<section class="section"><div class="section-head"><div><p class="eyebrow">TRACE & OTEL</p><h2>{s['input_artifacts']} 轮输入的可观测性</h2></div><p>每个 Case 下方可以展开查看输入、mapped request、Agent 输出、framework trace、OTEL span、submission 与 Judge。</p></div>
<div class="cards">
<div class="metric"><strong>{s['input_artifacts']}</strong><span>落盘 Input artifacts</span></div><div class="metric"><strong>{s['input_statuses'].get('succeeded',0)}</strong><span>Agent Input succeeded</span></div><div class="metric"><strong>{s['otel_spans']:,}</strong><span>OTEL spans</span></div><div class="metric"><strong>{s['framework_spans']:,}</strong><span>framework spans</span></div><div class="metric"><strong>{s['otel_statuses'].get('complete',0)}</strong><span>OTEL complete</span></div>
</div>
<p class="callout warn">{s['submitted_steps']} 个已提交步骤中有 {s['trace_partial_steps']} 个 trace capture 是 `partial`：{e(json.dumps(trace_reasons, ensure_ascii=False))}。主要原因是 SDK allowlist 丢弃了部分属性；这属于 trace 保真度警告，不等于 Case 失败。严格跑通的 Judge 报告没有 evidence gap。</p>
</section>

<section class="section"><div class="section-head"><div><p class="eyebrow">INTEGRATION</p><h2>Benchmark 前的原生接入诊断</h2></div><p>这 {len(data['native_observations'])} 次观察不计入 {s['attempts']} 次 Case attempt。它们用于定位网络声明、第三方限流和 trace 接受问题。</p></div>{_native_table(data)}</section>

<section class="section"><div class="section-head"><div><p class="eyebrow">REFERENCE SUITE</p><h2>最完整的一次 3 Agents × 5 Cases</h2></div><p>{e(live.get('suite_id'))}</p></div>
<div class="cards"><div class="metric"><strong>{live_counts.get('executed_cases','—')}</strong><span>Cases 全部执行完成</span></div><div class="metric"><strong>{live_counts.get('actual_inputs','—')}</strong><span>Inputs</span></div><div class="metric"><strong>{live_counts.get('judge_reports','—')}</strong><span>Judge reports</span></div><div class="metric"><strong>{live.get('concurrency',{}).get('observed_case_lifecycle_peak','—')}</strong><span>实测并发峰值</span></div><div class="metric"><strong>{num(live.get('total_elapsed_seconds'),1)}s</strong><span>Suite wall time</span></div></div>
<p class="callout">该套件没有 CaseGen、Agent execution、Judge service、host validation 或 cleanup 失败。Judge 为 13 issue、1 insufficient_evidence、1 pass。按本报告严格口径，证据不足的 1 次不计入 128 个 healthy，所以这里是 14/15 严格跑通；原审计中的“执行完成 15”使用了较宽的执行口径。</p>
</section>

<section class="section"><div class="section-head"><div><p class="eyebrow">COST</p><h2>已观测的模型用量</h2></div></div>
<div class="grid two"><section class="panel"><h3>OpenRouter</h3><p><strong>{integer(usage.get('openrouter_responses'))}</strong> responses<br><strong>{integer(usage.get('reported_total_tokens'))}</strong> tokens<br><strong>${e(usage.get('reported_cost_usd','—'))}</strong> provider-reported subtotal</p></section><section class="panel"><h3>KUMA</h3><p>CaseGen/Judge 的 token 与费用没有在本地 artifacts 中暴露，因此不能把 OpenRouter 小计声称为整次 campaign 总费用。</p><p class="muted">另有 {usage.get('responses_without_cost','—')} 个 OpenRouter response 没有返回 cost 字段。</p></section></div>
</section>

<section class="section"><div class="section-head"><div><p class="eyebrow">RUN LEDGER</p><h2>{s['runs']} 个 Run 的完成情况</h2></div><p>{run_counts.get('complete',0)} 完整跑通、{run_counts.get('partial',0)} 部分跑通、{run_counts.get('failed',0)} 全部失败、{run_counts.get('preparation_failed',0)} 准备失败。完整跑通要求计划的每个 Case 都严格 healthy。</p></div>{_run_table(data)}</section>

{_case_explorer(data)}

<footer><h3>来源与限制</h3><ul>{sources}</ul><p>报告对 API key、Authorization、Cookie、token、password 等字段进行递归脱敏。网络响应 body 不嵌入 HTML。原始 artifact 链接指向本机仓库；移动 HTML 时需保持它位于 results/analysis/。</p></footer>
</main>
<script>
const cards=[...document.querySelectorAll('.case-card')]; const search=document.getElementById('search'); const buttons=[...document.querySelectorAll('#filters button')]; const count=document.getElementById('visible-count'); let filter='all';
function apply(){{const q=search.value.trim().toLowerCase();let n=0;cards.forEach(card=>{{const okFilter=filter==='all'||card.dataset.filter.split(' ').includes(filter);const okSearch=!q||card.dataset.search.includes(q);const show=okFilter&&okSearch;card.hidden=!show;if(show)n++;}});count.textContent=`显示 ${{n}} / ${{cards.length}} 次 attempt`;}}
buttons.forEach(button=>button.addEventListener('click',()=>{{buttons.forEach(b=>b.classList.remove('active'));button.classList.add('active');filter=button.dataset.value;apply();}}));search.addEventListener('input',apply);apply();
</script></body></html>"""
