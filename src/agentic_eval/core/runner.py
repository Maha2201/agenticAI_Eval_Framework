"""Runner: drives conversations, builds traces, runs metrics.

The runner is the only component that sees connectors, adapters and metrics
together, and it knows nothing about any application.
"""

from __future__ import annotations

import logging
import time
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from agentic_eval import __version__
from agentic_eval.core import registry
from agentic_eval.core.config import ApplicationConfig, MetricRef
from agentic_eval.core.matching import ResolutionContext, UnresolvedReference, resolve
from agentic_eval.core.results import (
    CaseStatus,
    MetricResult,
    MetricStatus,
    RunResult,
    TestCaseResult,
)
from agentic_eval.core.testcase import TestCase
from agentic_eval.core.trace import Trace
from agentic_eval.interfaces.adapter import Adapter
from agentic_eval.interfaces.connector import Connector
from agentic_eval.interfaces.judge import Judge
from agentic_eval.interfaces.metric import Metric, MetricContext
from agentic_eval.metrics._common import missing_capabilities

log = logging.getLogger("agentic_eval")


@dataclass
class RunOptions:
    record_dir: Path | None = None  # save raw responses while running live
    replay_dir: Path | None = None  # run from saved responses instead of the app
    use_judge: bool = True
    include_tags: set[str] = field(default_factory=set)
    exclude_tags: set[str] = field(default_factory=set)
    case_ids: set[str] = field(default_factory=set)
    keep_raw: bool = False  # keep raw responses inside traces in the report


class Runner:
    def __init__(self, app: ApplicationConfig, options: RunOptions | None = None) -> None:
        self.app = app
        self.options = options or RunOptions()
        self.connector = self._build_connector()
        self.adapter: Adapter = registry.create(
            "adapter", app.adapter.plugin, base_dir=app.base_dir, options=app.adapter.options
        )
        self.judge: Judge | None = None
        if app.judge and self.options.use_judge:
            self.judge = registry.create(
                "judge", app.judge.plugin, base_dir=app.base_dir, options=app.judge.options
            )

    # ------------------------------------------------------------------ setup

    def _build_connector(self) -> Connector:
        from agentic_eval.connectors.replay import RecordingConnector

        if self.options.replay_dir is not None:
            return registry.create("connector", "replay",
                                   options={"dir": str(self.options.replay_dir)})
        live: Connector = registry.create(
            "connector", self.app.connector.plugin, base_dir=self.app.base_dir,
            options=self.app.connector.options,
        )
        if self.options.record_dir is not None:
            return RecordingConnector(live, self.options.record_dir)
        return live

    def _metrics_for(self, case: TestCase) -> list[Metric]:
        selected: dict[str, MetricRef] = {}
        # 1. app defaults
        for ref in self.app.default_metrics:
            selected[ref.name] = ref
        # 2. auto-activated by expectations present in the case
        for name in registry.available("metric")["metric"]:
            cls = registry.resolve("metric", name)
            if name not in selected and cls().applies_to(case):
                selected[name] = MetricRef(name=name)
        # 3. explicit case overrides (can add, retune or disable)
        for ov in case.metrics:
            if not ov.enabled:
                selected.pop(ov.name, None)
                continue
            base = selected.get(ov.name, MetricRef(name=ov.name))
            selected[ov.name] = MetricRef(
                name=ov.name,
                threshold=ov.threshold if ov.threshold is not None else base.threshold,
                options={**base.options, **ov.options},
            )
        metrics = []
        for ref in selected.values():
            cls = registry.resolve("metric", ref.name, base_dir=self.app.base_dir)
            metrics.append(cls(threshold=ref.threshold, **ref.options))
        return metrics

    def select(self, cases: Iterable[TestCase]) -> list[TestCase]:
        out = []
        for c in cases:
            if c.application and c.application != self.app.name:
                continue
            if self.options.case_ids and c.id not in self.options.case_ids:
                continue
            if self.options.include_tags and not (self.options.include_tags & set(c.tags)):
                continue
            if self.options.exclude_tags & set(c.tags):
                continue
            out.append(c)
        return out

    # -------------------------------------------------------------- execution

    def execute_conversation(self, case: TestCase) -> Trace:
        trace = Trace(
            application=self.app.name,
            test_case_id=case.id,
            capabilities=set(self.adapter.capabilities),
            entry_agent=self.app.entry_agent,
        )
        session = self.connector.open_session(case.id)
        try:
            for i, scripted in enumerate(case.turns):
                session.turn_index = i
                ctx = ResolutionContext(state=trace.final_state, vars=case.vars)
                try:
                    message = resolve(scripted.user, ctx)
                except UnresolvedReference as exc:
                    raise RuntimeError(
                        f"turn {i}: user message references {exc.args[0]}, "
                        "which the conversation has not produced yet"
                    ) from exc
                started = time.perf_counter()
                raw = self.connector.send(session, str(message))
                measured = (time.perf_counter() - started) * 1000
                if raw.latency_ms is None:
                    raw.latency_ms = measured
                turn = self.adapter.to_turn(raw, index=i, user_input=str(message))
                if turn.latency_ms is None:
                    turn.latency_ms = raw.latency_ms
                if not self.options.keep_raw:
                    turn.raw = None
                    for event in turn.events:
                        event.raw = None
                trace.turns.append(turn)
                manifest = self.adapter.agent_manifest(raw)
                if manifest:
                    trace.agents.update(manifest)
                trace.metadata.update(self.adapter.trace_metadata(raw))
            trace.session_id = session.session_id
        finally:
            self.connector.close_session(session)
        return trace

    def evaluate(self, trace: Trace, case: TestCase) -> list[MetricResult]:
        ctx = MetricContext(app=self.app, judge=self.judge)
        results = []
        for metric in self._metrics_for(case):
            missing = missing_capabilities(metric, trace)
            if missing:
                results.append(MetricResult.not_applicable(
                    metric.name, f"adapter does not provide: {', '.join(missing)}"))
                continue
            try:
                results.append(metric.evaluate(trace, case, ctx))
            except Exception as exc:  # a broken metric must not hide other results
                log.debug("metric %s crashed", metric.name, exc_info=True)
                results.append(MetricResult.error(metric.name, f"{type(exc).__name__}: {exc}"))
        return results

    def run_case(self, case: TestCase) -> TestCaseResult:
        started = time.perf_counter()
        base = dict(test_case_id=case.id, description=case.description, tags=case.tags)
        try:
            trace = self.execute_conversation(case)
        except Exception as exc:
            log.debug("case %s failed to execute", case.id, exc_info=True)
            return TestCaseResult(
                **base, status=CaseStatus.ERROR,
                error=f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=3)}",
                duration_ms=(time.perf_counter() - started) * 1000,
            )
        metrics = self.evaluate(trace, case)
        if any(m.status == MetricStatus.ERROR for m in metrics):
            status = CaseStatus.ERROR
        elif any(m.status == MetricStatus.FAILED for m in metrics):
            status = CaseStatus.FAILED
        else:
            status = CaseStatus.PASSED
        return TestCaseResult(**base, status=status, metrics=metrics, trace=trace,
                              duration_ms=(time.perf_counter() - started) * 1000)

    def run(self, cases: Iterable[TestCase], on_result: Any = None) -> RunResult:
        run = RunResult(run_id=uuid.uuid4().hex[:12], application=self.app.name,
                        framework_version=__version__)
        try:
            for case in self.select(cases):
                result = self.run_case(case)
                run.results.append(result)
                if on_result:
                    on_result(result)
        finally:
            self.connector.close()
        run.finished_at = datetime.now(timezone.utc)
        run.summarise()
        return run
