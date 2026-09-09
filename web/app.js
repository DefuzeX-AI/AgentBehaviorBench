const state = {
  data: null,
  selectedAgentId: null,
  filter: "",
  openSteps: new Map(),
  refreshing: false,
};

const requestedSuiteId = suiteIdFromPath();

const els = {
  stateBadge: document.querySelector("#stateBadge"),
  suiteId: document.querySelector("#suiteId"),
  resultPath: document.querySelector("#resultPath"),
  metricSelected: document.querySelector("#metricSelected"),
  metricPassed: document.querySelector("#metricPassed"),
  metricFailed: document.querySelector("#metricFailed"),
  metricEvents: document.querySelector("#metricEvents"),
  refreshButton: document.querySelector("#refreshButton"),
  lastUpdated: document.querySelector("#lastUpdated"),
  agentFilter: document.querySelector("#agentFilter"),
  agentList: document.querySelector("#agentList"),
  emptyState: document.querySelector("#emptyState"),
  agentDetail: document.querySelector("#agentDetail"),
};

els.agentFilter.addEventListener("input", (event) => {
  state.filter = event.target.value.trim().toLowerCase();
  render();
});

els.refreshButton.addEventListener("click", () => {
  refresh();
});

window.addEventListener("hashchange", () => {
  state.selectedAgentId = selectedFromHash();
  render();
});

refresh();

async function refresh() {
  if (state.refreshing) {
    return;
  }
  state.refreshing = true;
  updateRefreshButton();
  try {
    const apiPath = requestedSuiteId
      ? `/api/suites/${encodeURIComponent(requestedSuiteId)}/result`
      : "/api/result";
    const apiUrl = new URL(apiPath, window.location.origin);
    const response = await fetch(apiUrl, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    state.data = await response.json();
    if (requestedSuiteId && state.data.suite_id !== requestedSuiteId) {
      throw new Error(
        `Suite mismatch: requested ${requestedSuiteId}, received ${state.data.suite_id || "legacy"}`,
      );
    }
    state.lastUpdatedAt = new Date();
    if (!state.selectedAgentId) {
      state.selectedAgentId = selectedFromHash() || firstAgentId(state.data);
    }
    render();
  } catch (error) {
    renderError(error);
  } finally {
    state.refreshing = false;
    updateRefreshButton();
  }
}

function render() {
  if (!state.data) {
    return;
  }

  const data = state.data;
  const agents = data.agents || [];
  const selectedAgent =
    agents.find((item) => agentId(item) === state.selectedAgentId) || agents[0];
  if (selectedAgent) {
    state.selectedAgentId = agentId(selectedAgent);
  }

  renderHeader(data);
  renderMetrics(data);
  renderAgentList(agents);
  renderDetail(selectedAgent, data);
}

function renderHeader(data) {
  const suiteId = data.suite_id || "legacy";
  els.suiteId.textContent = `Suite ${suiteId}`;
  els.suiteId.title = data.suite_id
    ? `Suite ID: ${data.suite_id}`
    : "Legacy result without a Suite ID";
  els.resultPath.textContent = data.path || "";
  els.stateBadge.className = `badge ${stateClass(data.state)}`;
  els.stateBadge.textContent = stateLabel(data.state);
  els.lastUpdated.textContent = state.lastUpdatedAt
    ? `Updated ${formatTime(state.lastUpdatedAt)}`
    : "";
}

function renderMetrics(data) {
  const summary = data.summary || {};
  els.metricSelected.textContent =
    summary.selected ?? (data.selected_agent_ids || []).length;
  els.metricPassed.textContent = summary.passed ?? passedCount(data.agents || []);
  els.metricFailed.textContent = summary.failed ?? failedCount(data.agents || []);
  els.metricEvents.textContent = data.event_count ?? 0;
}

function renderAgentList(agents) {
  const filtered = agents.filter((item) =>
    agentId(item).toLowerCase().includes(state.filter),
  );

  els.agentList.replaceChildren(
    ...filtered.map((item) => {
      const id = agentId(item);
      const button = document.createElement("button");
      button.type = "button";
      button.className = `agent-button ${
        id === state.selectedAgentId ? "active" : ""
      }`;
      button.addEventListener("click", () => {
        state.selectedAgentId = id;
        window.location.hash = `agent=${encodeURIComponent(id)}`;
        render();
      });

      const name = document.createElement("span");
      name.className = "agent-name";
      name.textContent = id;

      const badge = document.createElement("span");
      badge.className = `badge ${agentStatusClass(item)}`;
      badge.textContent = agentStatusLabel(item);

      const meta = document.createElement("span");
      meta.className = "agent-meta";
      meta.textContent = agentMeta(item);

      button.append(name, badge, meta);
      return button;
    }),
  );
}

function renderDetail(item, data) {
  const hasAgent = Boolean(item);
  els.emptyState.hidden = hasAgent;
  els.agentDetail.hidden = !hasAgent;

  if (!item) {
    els.emptyState.textContent =
      data.state === "running_or_interrupted"
        ? "Waiting for completed agent results."
        : "No agent results found.";
    return;
  }

  const benchmark = item.benchmark || {};
  const report = benchmark.report || {};
  const steps = benchmark.steps || [];
  const stepEvents = item.step_events || [];
  const root = document.createElement("div");

  root.append(
    detailHeader(item),
    keyValuePanel("Run", [
      ["Adapter", benchmark.adapter_name || "n/a"],
      ["Run ID", benchmark.run_id || "n/a"],
      ["Run State", benchmark.run_state || "n/a"],
      ["Provider", benchmark.provider_mode || "n/a"],
      ["History Count", benchmark.history_count ?? "n/a"],
    ]),
    keyValuePanel("Report", [
      ["Status", report.status || "n/a"],
      ["Confidence", report.confidence ?? "n/a"],
      ["Issues", compactValue(report.issues || [])],
      ["Evidence Gaps", compactValue(report.evidence_gaps || [])],
    ]),
    stepsPanel(agentId(item), steps),
    stepEventsPanel(agentId(item), stepEvents),
  );

  if ((data.parse_errors || []).length > 0) {
    root.append(notice(`${data.parse_errors.length} JSON snapshot error(s). Some data could not be displayed.`));
  }
  if (data.suite_error) {
    root.append(
      notice(`${data.suite_error.type || "Error"}: ${data.suite_error.message || ""}`),
    );
  }

  els.agentDetail.replaceChildren(root);
}

function detailHeader(item) {
  const benchmark = item.benchmark || {};
  const header = document.createElement("div");
  header.className = "detail-header";

  const title = document.createElement("div");
  title.className = "detail-title";
  title.innerHTML = `
    <h2>${escapeHtml(agentId(item))}</h2>
    <div class="subtle">run=${escapeHtml(benchmark.run_id || "n/a")}</div>
  `;

  const badge = document.createElement("span");
  badge.className = `badge ${agentStatusClass(item)}`;
  badge.textContent = agentStatusLabel(item);

  header.append(title, badge);
  return header;
}

function keyValuePanel(title, rows) {
  const panel = document.createElement("section");
  panel.className = "panel";
  const heading = document.createElement("h3");
  heading.textContent = title;

  const body = document.createElement("div");
  body.className = "kv";
  for (const [key, value] of rows) {
    const keyNode = document.createElement("div");
    keyNode.textContent = key;
    const valueNode = document.createElement("div");
    valueNode.textContent = String(value);
    body.append(keyNode, valueNode);
  }

  panel.append(heading, body);
  return panel;
}

function stepsPanel(currentAgentId, steps) {
  const wrapper = document.createElement("section");
  wrapper.className = "steps";

  if (steps.length === 0) {
    wrapper.append(notice("No step data recorded for this agent."));
    return wrapper;
  }

  for (const [index, step] of steps.entries()) {
    const key = stepKey(currentAgentId, step, index);
    const details = document.createElement("details");
    details.open = state.openSteps.has(key) ? state.openSteps.get(key) : index === 0;
    details.addEventListener("toggle", () => {
      state.openSteps.set(key, details.open);
    });
    const summary = document.createElement("summary");
    summary.textContent = `Step ${index + 1}: ${step.input_id || "input"}`;

    const body = document.createElement("div");
    body.className = "step-body";
    body.append(
      jsonBlock("Payload", step.payload),
      jsonBlock("Output", step.output),
      jsonBlock("Raw Output", step.raw_output),
    );

    details.append(summary, body);
    wrapper.append(details);
  }

  return wrapper;
}

function stepEventsPanel(currentAgentId, events) {
  const wrapper = document.createElement("section");
  wrapper.className = "steps";

  if (events.length === 0) {
    return wrapper;
  }

  const title = document.createElement("div");
  title.className = "section-title";
  title.textContent = "Step Events";
  wrapper.append(title);

  for (const [index, event] of events.entries()) {
    const key = `${currentAgentId}:event:${index}`;
    const details = document.createElement("details");
    details.open = state.openSteps.has(key) ? state.openSteps.get(key) : false;
    details.addEventListener("toggle", () => {
      state.openSteps.set(key, details.open);
    });

    const summary = document.createElement("summary");
    summary.textContent = eventSummary(event, index);

    const body = document.createElement("div");
    body.className = "step-body";
    body.append(
      jsonBlock("Payload", event.payload || event.step?.payload || event.failure?.payload),
      jsonBlock("Output", event.step?.output || event.failure?.output),
      jsonBlock("Event", event),
    );

    details.append(summary, body);
    wrapper.append(details);
  }

  return wrapper;
}

function jsonBlock(title, value) {
  const block = document.createElement("div");
  block.className = "json-block";
  const heading = document.createElement("h4");
  heading.textContent = title;
  const pre = document.createElement("pre");
  pre.textContent = JSON.stringify(value ?? null, null, 2);
  block.append(heading, pre);
  return block;
}

function notice(text) {
  const node = document.createElement("div");
  node.className = "notice";
  node.textContent = text;
  return node;
}

function renderError(error) {
  els.stateBadge.className = "badge fail";
  els.stateBadge.textContent = "Error";
  els.lastUpdated.textContent = "Refresh failed";
  els.emptyState.hidden = false;
  els.agentDetail.hidden = true;
  els.emptyState.textContent = error.message;
}

function updateRefreshButton() {
  els.refreshButton.disabled = state.refreshing;
  els.refreshButton.textContent = state.refreshing ? "Loading" : "Refresh";
}

function agentId(item) {
  return item.agent_id || "unknown-agent";
}

function suiteIdFromPath() {
  const match = window.location.pathname.match(/^\/suite\/([^/]+)\/?$/);
  return match ? decodeURIComponent(match[1]) : null;
}

function agentStatusClass(item) {
  if (item.error) {
    return "fail";
  }
  return item.benchmark && item.benchmark.passed ? "pass" : "fail";
}

function agentStatusLabel(item) {
  if (item.error) {
    return "ERROR";
  }
  return item.benchmark && item.benchmark.passed ? "PASS" : "FAIL";
}

function agentMeta(item) {
  if (item.error) {
    return `${item.error.type || "Error"}: ${item.error.message || ""}`;
  }
  const benchmark = item.benchmark || {};
  const steps = (benchmark.steps || []).length;
  return `${benchmark.adapter_name || "adapter"} | ${steps} step(s)`;
}

function firstAgentId(data) {
  return data && data.agents && data.agents[0] ? agentId(data.agents[0]) : null;
}

function selectedFromHash() {
  const match = window.location.hash.match(/agent=([^&]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

function passedCount(agents) {
  return agents.filter((item) => !item.error && item.benchmark?.passed).length;
}

function failedCount(agents) {
  return agents.filter((item) => item.error || !item.benchmark?.passed).length;
}

function compactValue(value) {
  if (Array.isArray(value)) {
    return value.length === 0 ? "none" : value.map((item) => String(item)).join("; ");
  }
  if (value && typeof value === "object") {
    return JSON.stringify(value);
  }
  return value ?? "none";
}

function stateClass(value) {
  if (value === "complete") {
    return "pass";
  }
  if (value === "failed") {
    return "fail";
  }
  return "warn";
}

function stateLabel(value) {
  if (value === "complete") {
    return "Complete";
  }
  if (value === "failed") {
    return "Failed";
  }
  return "Running or interrupted";
}

function stepKey(currentAgentId, step, index) {
  return `${currentAgentId}:${step.input_id || index}`;
}

function eventSummary(event, index) {
  const inputId = event.input_id || event.step?.input_id || event.failure?.input_id || "input";
  return `Event ${index + 1}: ${event.event || "step"} | ${inputId}`;
}

function formatTime(date) {
  return date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => {
    const entities = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    };
    return entities[char];
  });
}
