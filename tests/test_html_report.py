"""HTML report: self-contained, safe embedding, rebuildable from run.json."""

import json
import re

from agentic_eval.cli import main
from agentic_eval.core import registry
from agentic_eval.core.results import RunResult
from agentic_eval.reporting import write_html


def _run(replay_runner, demo_cases, reason="ok"):
    replay_runner.judge = registry.create("judge", "static", options={"score": 0.03, "reason": reason})
    return replay_runner.run(demo_cases.values())


def _embedded(html):
    m = re.search(r'<script id="run-data" type="application/json">(.*?)</script>', html, re.S)
    assert m, "run data block missing"
    return json.loads(m.group(1).replace("<\\/", "</").replace("<\\!--", "<!--"))


def test_self_contained_and_data_round_trips(replay_runner, demo_cases, tmp_path):
    run = _run(replay_runner, demo_cases)
    html = write_html(run, tmp_path / "report.html").read_text(encoding="utf-8")
    assert not re.search(r'(src|href)="https?://', html), "report must not load external resources"
    data = _embedded(html)
    assert data["exit_code"] == run.exit_code == 2
    assert {r["test_case_id"] for r in data["results"]} == set(demo_cases)


def test_model_text_cannot_close_the_script(replay_runner, demo_cases, tmp_path):
    evil = "done </script><script>alert(1)</script> <!-- x"
    run = _run(replay_runner, demo_cases, reason=evil)
    html = write_html(run, tmp_path / "report.html").read_text(encoding="utf-8")
    assert html.count("</script>") == 2  # only the page's own two script elements
    rubric = next(m for r in _embedded(html)["results"] for m in r["metrics"] if m["name"] == "llm_rubric")
    assert rubric["reason"] == evil


def test_report_command_rebuilds_from_run_json(replay_runner, demo_cases, tmp_path):
    run = _run(replay_runner, demo_cases)
    (tmp_path / "run.json").write_text(run.model_dump_json(), encoding="utf-8")
    assert main(["report", str(tmp_path)]) == 0
    assert (tmp_path / "report.html").exists() and (tmp_path / "report.md").exists()
    again = RunResult.model_validate_json((tmp_path / "run.json").read_text(encoding="utf-8"))
    assert len(again.results) == len(run.results)
