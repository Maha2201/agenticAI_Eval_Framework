"""Self-contained HTML report.

One file, no external resources (no CDN, no fonts, no images), so it opens
offline and behind corporate proxies. The run is embedded as JSON and rendered
in the browser with plain JavaScript. All application and model text is
inserted with ``textContent``, never as HTML, because transcripts contain
untrusted model output.
"""

from __future__ import annotations

import json
from pathlib import Path

from agentic_eval.core.results import RunResult


def write_html(run: RunResult, path: Path) -> Path:
    payload = json.loads(run.model_dump_json())
    payload["exit_code"] = run.exit_code
    data = json.dumps(payload, ensure_ascii=False)
    # Stop any "</script>" inside the data from closing the script element.
    data = data.replace("</", "<\\/").replace("<!--", "<\\!--")
    html = _TEMPLATE.replace("__TITLE__", _escape(f"{run.application} — run {run.run_id}"))
    html = html.replace("__DATA__", data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path


def _escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root {
  --bg: #f6f7f9; --panel: #ffffff; --text: #1d2330; --muted: #5d6677; --line: #e1e5ec;
  --pass: #1f8a4c; --pass-bg: #e3f4ea; --fail: #c62f2f; --fail-bg: #fbe5e5;
  --na: #6b7280; --na-bg: #eef0f3; --err: #a35b00; --err-bg: #fdf0dc;
  --accent: #2f5bd3; --accent-bg: #e8eefc; --code: #f1f3f6; --judge: #7a3fc2; --judge-bg: #f1e8fb;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #12151b; --panel: #1a1f27; --text: #e6e9ef; --muted: #9aa3b2; --line: #2b3240;
    --pass: #4cc282; --pass-bg: #163325; --fail: #f07070; --fail-bg: #3a1c1c;
    --na: #9aa3b2; --na-bg: #252b36; --err: #f0a64a; --err-bg: #3a2a14;
    --accent: #7ea2ff; --accent-bg: #1f2a45; --code: #222833; --judge: #c39af2; --judge-bg: #2c2140;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text);
  font: 14px/1.5 "Segoe UI", system-ui, -apple-system, Roboto, Arial, sans-serif; }
main { max-width: 1280px; margin: 0 auto; padding: 24px 20px 64px; }
h1 { font-size: 22px; margin: 0 0 4px; }
h2 { font-size: 16px; margin: 32px 0 12px; }
h3 { font-size: 14px; margin: 18px 0 8px; }
.muted { color: var(--muted); }
.small { font-size: 12px; }
.panel { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 16px; }
.banner { display: flex; align-items: center; gap: 12px; padding: 12px 16px; border-radius: 10px;
  margin: 16px 0; font-weight: 600; }
.banner.ok { background: var(--pass-bg); color: var(--pass); }
.banner.fail { background: var(--fail-bg); color: var(--fail); }
.banner.err { background: var(--err-bg); color: var(--err); }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 14px; }
.card .n { font-size: 26px; font-weight: 700; }
.card.pass .n { color: var(--pass); } .card.fail .n { color: var(--fail); } .card.err .n { color: var(--err); }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: 7px 8px; border-bottom: 1px solid var(--line); vertical-align: top; }
th { font-size: 12px; color: var(--muted); font-weight: 600; white-space: nowrap; }
.scroll { overflow-x: auto; }
.bar { height: 10px; background: var(--na-bg); border-radius: 5px; overflow: hidden; min-width: 120px; }
.bar > span { display: block; height: 100%; background: var(--pass); }
.badge { display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 12px; font-weight: 600;
  white-space: nowrap; }
.b-passed { background: var(--pass-bg); color: var(--pass); }
.b-failed { background: var(--fail-bg); color: var(--fail); }
.b-not_applicable { background: var(--na-bg); color: var(--na); }
.b-error { background: var(--err-bg); color: var(--err); }
.b-judge { background: var(--judge-bg); color: var(--judge); }
.b-tag { background: var(--accent-bg); color: var(--accent); font-weight: 500; }
.matrix td.cell { text-align: center; font-variant-numeric: tabular-nums; cursor: pointer; min-width: 64px; }
.matrix td.c-passed { background: var(--pass-bg); color: var(--pass); }
.matrix td.c-failed { background: var(--fail-bg); color: var(--fail); font-weight: 700; }
.matrix td.c-not_applicable { background: var(--na-bg); color: var(--na); }
.matrix td.c-error { background: var(--err-bg); color: var(--err); }
.matrix td.c-none { color: var(--line); }
.matrix th.rot { writing-mode: vertical-rl; transform: rotate(180deg); vertical-align: bottom; height: 150px; }
.filters { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 12px; }
.filters button, .filters select, .filters input { font: inherit; padding: 5px 10px; border-radius: 8px;
  border: 1px solid var(--line); background: var(--panel); color: var(--text); }
.filters button.on { background: var(--accent); border-color: var(--accent); color: #fff; }
.filters input { min-width: 220px; }
details.case { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; margin-bottom: 10px; }
details.case > summary { cursor: pointer; padding: 12px 16px; display: flex; gap: 10px; align-items: center;
  flex-wrap: wrap; list-style: none; }
details.case > summary::-webkit-details-marker { display: none; }
details.case > summary::before { content: "▸"; color: var(--muted); }
details.case[open] > summary::before { content: "▾"; }
details.case .body { padding: 0 16px 16px; border-top: 1px solid var(--line); }
.path { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.chip { padding: 2px 10px; border-radius: 12px; background: var(--accent-bg); color: var(--accent); font-size: 12px; }
.arrow { color: var(--muted); }
.judge { border-left: 3px solid var(--judge); background: var(--judge-bg); padding: 10px 14px; border-radius: 6px;
  margin: 12px 0; }
.judge ol { margin: 6px 0 6px 18px; padding: 0; }
.warn { color: var(--err); font-weight: 600; }
.turn { border: 1px solid var(--line); border-radius: 8px; margin: 10px 0; overflow: hidden; }
.turn-head { display: flex; gap: 10px; flex-wrap: wrap; padding: 6px 10px; background: var(--code);
  font-size: 12px; color: var(--muted); }
.ev { display: grid; grid-template-columns: 130px 1fr; gap: 10px; padding: 6px 10px;
  border-top: 1px solid var(--line); }
.ev .k { font-size: 12px; font-weight: 600; color: var(--muted); }
.ev.user .k { color: var(--accent); }
.ev.message .k { color: var(--pass); }
.ev.tool_call .k, .ev.tool_result .k { color: var(--judge); }
.ev.handoff .k { color: var(--accent); }
.ev.rejected .k, .ev.gfail .k, .ev.error .k { color: var(--fail); }
.ev.rejected, .ev.gfail { background: var(--fail-bg); }
pre { margin: 4px 0 0; padding: 8px 10px; background: var(--code); border-radius: 6px; overflow-x: auto;
  font: 12px/1.45 Consolas, "Cascadia Mono", Menlo, monospace; white-space: pre-wrap; word-break: break-word; }
.reason { white-space: pre-wrap; word-break: break-word; }
.empty { padding: 24px; text-align: center; color: var(--muted); }
footer { margin-top: 40px; font-size: 12px; color: var(--muted); }
</style>
</head>
<body>
<main id="app"></main>
<script id="run-data" type="application/json">__DATA__</script>
<script>
(function () {
  "use strict";
  var RUN = JSON.parse(document.getElementById("run-data").textContent);
  var app = document.getElementById("app");

  // ---------- helpers (text only; never innerHTML with run data) ----------
  function el(tag, attrs) {
    var node = document.createElement(tag);
    if (attrs) for (var k in attrs) {
      if (k === "text") node.textContent = attrs[k];
      else if (k === "cls") node.className = attrs[k];
      else if (k.slice(0, 2) === "on") node.addEventListener(k.slice(2), attrs[k]);
      else node.setAttribute(k, attrs[k]);
    }
    for (var i = 2; i < arguments.length; i++) add(node, arguments[i]);
    return node;
  }
  function add(node, child) {
    if (child === null || child === undefined || child === false) return;
    if (Array.isArray(child)) { child.forEach(function (c) { add(node, c); }); return; }
    node.appendChild(typeof child === "object" ? child : document.createTextNode(String(child)));
  }
  function badge(status, label) {
    return el("span", { cls: "badge b-" + status, text: label || LABEL[status] || status });
  }
  function fmt(n, d) { return n === null || n === undefined ? "" : Number(n).toFixed(d === undefined ? 2 : d); }
  function pct(x) { return Math.round(x * 100) + "%"; }
  function json(v) { return JSON.stringify(v, null, 2); }
  function slug(s) { return "case-" + String(s).replace(/[^A-Za-z0-9_-]/g, "_"); }
  var LABEL = { passed: "pass", failed: "FAIL", not_applicable: "n/a", error: "ERROR" };

  var results = RUN.results || [];
  var summary = RUN.summary || {};

  // metric names in first-seen order
  var metricNames = [];
  results.forEach(function (r) { (r.metrics || []).forEach(function (m) {
    if (metricNames.indexOf(m.name) < 0) metricNames.push(m.name); }); });
  var judgeMetrics = {};
  results.forEach(function (r) { (r.metrics || []).forEach(function (m) {
    if (m.deterministic === false) judgeMetrics[m.name] = true; }); });

  // ---------- header ----------
  var started = RUN.started_at ? new Date(RUN.started_at) : null;
  var finished = RUN.finished_at ? new Date(RUN.finished_at) : null;
  var duration = started && finished ? ((finished - started) / 1000).toFixed(1) + " s" : "";
  add(app, el("h1", { text: "Evaluation report: " + RUN.application }));
  add(app, el("div", { cls: "muted small" },
    "Run ", el("b", { text: RUN.run_id }), " · framework " + (RUN.framework_version || "?"),
    started ? " · started " + started.toLocaleString() : "", duration ? " · duration " + duration : ""));

  var ec = RUN.exit_code;
  var bannerCls = ec === 0 ? "ok" : ec === 2 ? "fail" : "err";
  var bannerText = ec === 0 ? "All test cases passed"
    : ec === 2 ? "Threshold breach: " + summary.failed + " test case(s) failed"
    : "Harness error: " + summary.errors + " case(s) could not be evaluated; results are incomplete";
  add(app, el("div", { cls: "banner " + bannerCls }, bannerText,
    el("span", { cls: "small", style: "margin-left:auto;font-weight:500", text: "exit code " + ec })));

  // ---------- summary cards ----------
  var naCount = 0, judgeCount = 0;
  results.forEach(function (r) { (r.metrics || []).forEach(function (m) {
    if (m.status === "not_applicable") naCount++;
    if (m.deterministic === false && m.score !== null) judgeCount++; }); });
  var passRate = summary.total ? summary.passed / summary.total : 0;
  add(app, el("div", { cls: "cards" },
    card("", summary.total, "test cases"),
    card("pass", summary.passed, "passed"),
    card("fail", summary.failed, "failed"),
    card("err", summary.errors, "errors"),
    card("", pct(passRate), "case pass rate"),
    card("", naCount, "metrics not applicable"),
    card("", judgeCount, "judge-scored results")));
  function card(cls, n, label) {
    return el("div", { cls: "card " + cls }, el("div", { cls: "n", text: n }), el("div", { cls: "muted small", text: label }));
  }

  // ---------- metric overview ----------
  add(app, el("h2", { text: "Metrics" }));
  var mt = el("table");
  add(mt, el("tr", null, ["Metric", "Type", "Pass rate", "", "Pass", "Fail", "n/a", "Error"].map(function (h) {
    return el("th", { text: h }); })));
  metricNames.forEach(function (name) {
    var c = { passed: 0, failed: 0, not_applicable: 0, error: 0 };
    results.forEach(function (r) { (r.metrics || []).forEach(function (m) { if (m.name === name) c[m.status]++; }); });
    var scored = c.passed + c.failed;
    var rate = scored ? c.passed / scored : null;
    add(mt, el("tr", null,
      el("td", null, el("b", { text: name })),
      el("td", null, judgeMetrics[name] ? badge("judge", "LLM judge") : el("span", { cls: "muted small", text: "deterministic" })),
      el("td", null, el("div", { cls: "bar" }, el("span", { style: "width:" + (rate === null ? 0 : rate * 100) + "%" }))),
      el("td", { cls: "small", text: rate === null ? "not scored" : pct(rate) }),
      el("td", { text: c.passed || "" }), el("td", { text: c.failed || "" }),
      el("td", { text: c.not_applicable || "" }), el("td", { text: c.error || "" })));
  });
  add(app, el("div", { cls: "panel scroll" }, mt));

  // ---------- matrix ----------
  add(app, el("h2", { text: "Case × metric matrix" }));
  add(app, el("div", { cls: "muted small", style: "margin:-6px 0 10px",
    text: "Cells show the score; click a cell to open that case." }));
  var mx = el("table", { cls: "matrix" });
  add(mx, el("tr", null, el("th", { text: "Test case" }), el("th", { text: "Status" }),
    metricNames.map(function (n) { return el("th", { cls: "rot", text: n }); })));
  results.forEach(function (r) {
    var byName = {};
    (r.metrics || []).forEach(function (m) { byName[m.name] = m; });
    add(mx, el("tr", null,
      el("td", null, el("a", { href: "#" + slug(r.test_case_id), text: r.test_case_id, onclick: openCase(r.test_case_id) })),
      el("td", null, badge(r.status === "passed" ? "passed" : r.status === "failed" ? "failed" : "error",
        r.status.toUpperCase())),
      metricNames.map(function (n) {
        var m = byName[n];
        if (!m) return el("td", { cls: "cell c-none", text: "·" });
        var label = m.status === "not_applicable" ? "n/a" : m.status === "error" ? "ERR" : fmt(m.score);
        return el("td", { cls: "cell c-" + m.status, title: n + ": " + (m.reason || ""), text: label,
          onclick: openCase(r.test_case_id) });
      })));
  });
  add(app, el("div", { cls: "panel scroll" }, mx));

  // ---------- filters ----------
  add(app, el("h2", { text: "Test cases" }));
  var state = { status: "all", tag: "", q: "" };
  var tags = [];
  results.forEach(function (r) { (r.tags || []).forEach(function (t) { if (tags.indexOf(t) < 0) tags.push(t); }); });
  tags.sort();
  var statusButtons = {};
  var filters = el("div", { cls: "filters" });
  ["all", "passed", "failed", "error"].forEach(function (s) {
    var b = el("button", { text: s === "all" ? "All" : LABEL[s] === "pass" ? "Passed" : s === "failed" ? "Failed" : "Errors",
      onclick: function () { state.status = s; render(); } });
    statusButtons[s] = b; add(filters, b);
  });
  var tagSel = el("select", { onchange: function (e) { state.tag = e.target.value; render(); } },
    el("option", { value: "", text: "All tags" }), tags.map(function (t) { return el("option", { value: t, text: t }); }));
  var search = el("input", { type: "search", placeholder: "Search id, description, reason…",
    oninput: function (e) { state.q = e.target.value.toLowerCase(); render(); } });
  var expandAll = el("button", { text: "Expand all", onclick: function () { toggleAll(true); } });
  var collapseAll = el("button", { text: "Collapse all", onclick: function () { toggleAll(false); } });
  add(filters, [tagSel, search, expandAll, collapseAll]);
  add(app, filters);
  var list = el("div");
  add(app, list);

  var caseNodes = results.map(buildCase);
  function toggleAll(open) { caseNodes.forEach(function (c) { if (c.node.style.display !== "none") c.node.open = open; }); }
  function openCase(id) {
    return function (e) {
      e.preventDefault();
      state.status = "all"; state.tag = ""; state.q = ""; tagSel.value = ""; search.value = ""; render();
      var c = caseNodes.filter(function (x) { return x.id === id; })[0];
      if (c) { c.node.open = true; c.node.scrollIntoView({ behavior: "smooth", block: "start" }); }
    };
  }
  function render() {
    Object.keys(statusButtons).forEach(function (s) { statusButtons[s].className = state.status === s ? "on" : ""; });
    var shown = 0;
    caseNodes.forEach(function (c) {
      var r = c.result, ok = true;
      if (state.status !== "all" && r.status !== state.status) ok = false;
      if (state.tag && (r.tags || []).indexOf(state.tag) < 0) ok = false;
      if (state.q && c.haystack.indexOf(state.q) < 0) ok = false;
      c.node.style.display = ok ? "" : "none";
      if (ok) shown++;
    });
    empty.style.display = shown ? "none" : "";
  }
  caseNodes.forEach(function (c) { add(list, c.node); });
  var empty = el("div", { cls: "panel empty", text: "No test cases match the filters." });
  add(list, empty);
  render();

  // ---------- one case ----------
  function buildCase(r) {
    var trace = r.trace || null;
    var statusKey = r.status === "passed" ? "passed" : r.status === "failed" ? "failed" : "error";
    var failing = (r.metrics || []).filter(function (m) { return m.status === "failed" || m.status === "error"; })
      .map(function (m) { return m.name; });
    var summaryRow = el("summary", null,
      badge(statusKey, r.status.toUpperCase()), el("b", { text: r.test_case_id }),
      (r.tags || []).map(function (t) { return badge("tag", t); }),
      failing.length ? el("span", { cls: "small", style: "color:var(--fail)", text: "failed: " + failing.join(", ") }) : null,
      r.duration_ms ? el("span", { cls: "muted small", style: "margin-left:auto", text: (r.duration_ms / 1000).toFixed(2) + " s" }) : null);
    var body = el("div", { cls: "body" });
    if (r.description) add(body, el("p", { text: r.description }));

    if (r.error) {
      add(body, el("h3", { text: "Error" }), el("pre", { text: r.error }));
    }

    if (trace) {
      var path = agentPath(trace);
      var tools = [];
      (trace.turns || []).forEach(function (t) { (t.events || []).forEach(function (e) {
        if (e.type === "tool_call") tools.push(e.tool); }); });
      add(body, el("div", { cls: "path", style: "margin:8px 0" },
        el("span", { cls: "muted small", text: "Agent path:" }),
        path.length ? path.map(function (a, i) { return [i ? el("span", { cls: "arrow", text: "→" }) : null, el("span", { cls: "chip", text: a })]; })
          : el("span", { cls: "muted small", text: "(none)" }),
        el("span", { cls: "muted small", style: "margin-left:16px", text: "Tool calls: " + (tools.join(", ") || "(none)") })));
    }

    if ((r.metrics || []).length) {
      add(body, el("h3", { text: "Metrics" }));
      var t = el("table");
      add(t, el("tr", null, ["Metric", "Status", "Score", "Threshold", "Reason"].map(function (h) { return el("th", { text: h }); })));
      r.metrics.forEach(function (m) {
        add(t, el("tr", null,
          el("td", null, el("b", { text: m.name }), m.deterministic === false ? [" ", badge("judge", "judge")] : null),
          el("td", null, badge(m.status)),
          el("td", { text: fmt(m.score) }), el("td", { text: fmt(m.threshold) }),
          el("td", { cls: "reason", text: m.reason || "" })));
      });
      add(body, el("div", { cls: "scroll" }, t));
      r.metrics.filter(function (m) { return m.deterministic === false && m.score !== null; }).forEach(function (m) {
        add(body, judgeBlock(m));
      });
    }

    if (trace) {
      add(body, el("h3", { text: "Conversation" }));
      (trace.turns || []).forEach(function (turn) { add(body, turnBlock(turn)); });
      var fs = finalState(trace);
      if (Object.keys(fs).length) add(body, el("h3", { text: "Final state" }), el("pre", { text: json(fs) }));
    }

    var node = el("details", { cls: "case", id: slug(r.test_case_id) }, summaryRow, body);
    if (r.status !== "passed") node.open = false;
    var hay = [r.test_case_id, r.description || "", (r.tags || []).join(" "), r.error || ""]
      .concat((r.metrics || []).map(function (m) { return m.name + " " + (m.reason || ""); })).join(" ").toLowerCase();
    return { id: r.test_case_id, result: r, node: node, haystack: hay };
  }

  function judgeBlock(m) {
    var d = m.details || {};
    var steps = d.evaluation_steps || [];
    return el("div", { cls: "judge" },
      el("div", null, el("b", { text: "Judge audit: " + m.name }), " · score ", el("b", { text: fmt(m.score) }),
        " / threshold " + fmt(m.threshold) + " · judge ", el("code", { text: d.judge || "?" }),
        " · model ", el("code", { text: d.model || "?" })),
      d.warning ? el("div", { cls: "warn small", style: "margin-top:6px", text: "⚠ " + d.warning }) : null,
      d.criteria ? el("div", { style: "margin-top:6px" }, el("span", { cls: "muted", text: "Criteria: " }), d.criteria) : null,
      el("div", { style: "margin-top:6px" }, el("span", { cls: "muted", text: "Evaluation steps (" + (d.steps_source || "?") + "):" })),
      steps.length ? el("ol", null, steps.map(function (s) { return el("li", { text: s }); }))
        : el("div", { cls: "muted small", text: "(none recorded)" }),
      el("div", null, el("span", { cls: "muted", text: "Reason: " }), el("span", { cls: "reason", text: m.reason || "" })));
  }

  function turnBlock(turn) {
    var head = el("div", { cls: "turn-head" },
      el("b", { text: "Turn " + turn.index }),
      turn.active_agent ? el("span", { text: "ended with " + turn.active_agent }) : null,
      turn.latency_ms !== null && turn.latency_ms !== undefined ? el("span", { text: Math.round(turn.latency_ms) + " ms" }) : null,
      turn.blocked ? el("span", { style: "color:var(--fail);font-weight:600", text: "BLOCKED by guardrail" }) : null);
    var box = el("div", { cls: "turn" }, head, ev("user", "User", turn.user_input));
    (turn.events || []).forEach(function (e) { add(box, renderEvent(e)); });
    return box;
  }

  function ev(cls, label, content, pre) {
    return el("div", { cls: "ev " + cls }, el("div", { cls: "k", text: label }),
      pre ? el("div", null, pre) : el("div", { cls: "reason", text: content }));
  }

  function renderEvent(e) {
    var who = e.agent ? " · " + e.agent : "";
    switch (e.type) {
      case "message": return ev("message", "Agent" + (e.agent ? "" : ""), (e.agent ? "[" + e.agent + "] " : "") + e.content);
      case "tool_call": return ev("tool_call", "Tool call", null,
        [el("div", null, el("b", { text: e.tool }), el("span", { cls: "muted small", text: who })),
         Object.keys(e.arguments || {}).length ? el("pre", { text: json(e.arguments) }) : null]);
      case "tool_result": return ev("tool_result", "Tool result" + (e.kind && e.kind !== "data" ? " (" + e.kind + ")" : ""), null,
        [el("div", { cls: "muted small", text: (e.tool || "?") + who }),
         el("pre", { text: typeof e.output === "string" ? e.output : json(e.output) })]);
      case "handoff":
        if (e.status === "rejected") return ev("rejected", "Handoff REJECTED",
          (e.source || e.agent || "?") + " → " + (e.target || "?") + (e.reason ? "  ·  " + e.reason : ""));
        return ev("handoff", "Handoff", (e.source || "?") + " → " + (e.target || "?"));
      case "hook": return ev("hook", "Hook", e.name + (e.kind ? " (" + e.kind + ")" : "") + who);
      case "state_change": return ev("state_change", "State change", null, el("pre", { text: json(e.changes || {}) }));
      case "guardrail": return ev(e.passed ? "guardrail" : "gfail", "Guardrail " + (e.passed ? "passed" : "TRIPPED"),
        e.name + (e.reason ? "  ·  " + e.reason : ""));
      case "approval_request": return ev("approval", "Approval request", e.action + (e.details ? " " + json(e.details) : ""));
      case "approval_decision": return ev("approval", "Approval " + (e.approved ? "granted" : "denied"), e.action + (e.decided_by ? " by " + e.decided_by : ""));
      case "error": return ev("error", "Error", e.message);
      default: return ev("other", e.type || "event", json(e));
    }
  }

  function agentPath(trace) {
    var path = [];
    function push(a) { if (a && path[path.length - 1] !== a) path.push(a); }
    if (trace.entry_agent) push(trace.entry_agent);
    (trace.turns || []).forEach(function (t) { (t.events || []).forEach(function (e) {
      if (e.type === "handoff" && e.status !== "rejected") { push(e.source); push(e.target); }
      else if (!path.length && e.agent) push(e.agent);
    }); });
    return path;
  }

  function finalState(trace) {
    var s = {};
    (trace.turns || []).forEach(function (t) {
      if (t.state_after && Object.keys(t.state_after).length) s = Object.assign({}, t.state_after);
      else (t.events || []).forEach(function (e) { if (e.type === "state_change") Object.assign(s, e.changes || {}); });
    });
    return s;
  }

  add(app, el("footer", null, "Generated by agentic-eval " + (RUN.framework_version || "") +
    ". Self-contained file: no network access needed. Model output is shown as plain text."));
})();
</script>
</body>
</html>
"""
