"""JSON, Markdown and console reports."""

from __future__ import annotations

from pathlib import Path

from agentic_eval.core.results import CaseStatus, MetricStatus, RunResult, TestCaseResult

_ICON = {
    CaseStatus.PASSED: "PASS",
    CaseStatus.FAILED: "FAIL",
    CaseStatus.ERROR: "ERROR",
}
_M_ICON = {
    MetricStatus.PASSED: "pass",
    MetricStatus.FAILED: "FAIL",
    MetricStatus.NOT_APPLICABLE: "n/a",
    MetricStatus.ERROR: "ERROR",
}


def write_json(run: RunResult, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(run.model_dump_json(indent=2), encoding="utf-8")
    return path


def write_markdown(run: RunResult, path: Path) -> Path:
    s = run.summary
    lines = [
        f"# Evaluation report: {run.application}",
        "",
        f"Run `{run.run_id}`, framework {run.framework_version}, "
        f"started {run.started_at:%Y-%m-%d %H:%M:%S} UTC.",
        "",
        f"**{s.passed}/{s.total} passed**, {s.failed} failed, {s.errors} errors.",
        "",
        "## Metric pass rates",
        "",
        "| Metric | Pass rate |",
        "|---|---|",
        *[f"| {k} | {v:.0%} |" for k, v in s.metric_pass_rates.items()],
        "",
        "## Test cases",
        "",
    ]
    for r in run.results:
        lines += [f"### {_ICON[r.status]} — {r.test_case_id}", ""]
        if r.description:
            lines += [r.description, ""]
        if r.error:
            lines += ["```", r.error.strip(), "```", ""]
            continue
        lines += ["| Metric | Status | Score | Threshold | Reason |", "|---|---|---|---|---|"]
        for m in r.metrics:
            score = "" if m.score is None else f"{m.score:.2f}"
            thr = "" if m.threshold is None else f"{m.threshold:.2f}"
            reason = m.reason.replace("\n", " ").replace("|", "\\|")[:300]
            judge = " (judge)" if not m.deterministic else ""
            lines.append(f"| {m.name}{judge} | {_M_ICON[m.status]} | {score} | {thr} | {reason} |")
        for m in r.metrics:
            if m.deterministic or m.score is None:
                continue
            d = m.details
            lines += ["", f"**Judge audit: {m.name}** — score {m.score:.2f} / threshold "
                      f"{m.threshold:.2f}, judge `{d.get('judge', '?')}`, model `{d.get('model', '?')}`", ""]
            if d.get("warning"):
                lines += [f"> ⚠️ {d['warning']}", ""]
            lines += [f"Criteria: {d.get('criteria', '')}", "",
                      f"Evaluation steps ({d.get('steps_source', '?')}):", ""]
            steps = d.get("evaluation_steps") or []
            lines += [f"{i}. {st}" for i, st in enumerate(steps, 1)] or ["(none recorded)"]
            lines += ["", "Reason:", "", f"> {m.reason.strip()}"]
        if r.trace:
            lines += ["", f"Agent path: {' → '.join(r.trace.agent_path()) or '(none)'}  ",
                      f"Tool calls: {', '.join(c.tool for c in r.trace.tool_calls) or '(none)'}"]
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def console_line(r: TestCaseResult) -> str:
    head = f"[{_ICON[r.status]:5}] {r.test_case_id}"
    if r.error:
        return f"{head}\n        {r.error.strip().splitlines()[0]}"
    rows = [head]
    for m in r.metrics:
        if m.details.get("steps_source") == "generated":
            rows.append(f"        warn  {m.name}: judge generated its own steps; see report.md")
        if m.status == MetricStatus.PASSED:
            continue
        rows.append(f"        {_M_ICON[m.status]:5} {m.name}: {m.reason.splitlines()[0] if m.reason else ''}")
    return "\n".join(rows)


def console_summary(run: RunResult) -> str:
    s = run.summary
    return (f"\n{s.passed}/{s.total} passed, {s.failed} failed, {s.errors} errors "
            f"(exit code {run.exit_code})")
