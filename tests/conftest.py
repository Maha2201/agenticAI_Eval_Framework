from __future__ import annotations

from pathlib import Path

import pytest

from agentic_eval.core.config import load_application
from agentic_eval.core.runner import RunOptions, Runner
from agentic_eval.core.testcase import load_test_cases

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "applications" / "openai_cs_agents_demo"


@pytest.fixture()
def demo_app():
    return load_application(DEMO)


@pytest.fixture()
def demo_cases():
    return {c.id: c for c in load_test_cases(DEMO / "testcases")}


@pytest.fixture()
def replay_runner(demo_app):
    return Runner(demo_app, RunOptions(replay_dir=DEMO / "fixtures", use_judge=False))
