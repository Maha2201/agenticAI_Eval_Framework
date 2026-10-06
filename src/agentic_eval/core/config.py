"""Application configuration.

One YAML file per application under test. It names the connector, adapter and
judge plugins and their options, and declares facts about the application that
generic metrics need (entry agent, which tools change state). It contains no
test logic.

Environment variables are substituted before parsing: ``${NAME}`` or
``${NAME:-default}``. Secrets therefore live in the environment, never in the file.
"""

from __future__ import annotations

import os
import re
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

_ENV = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def substitute_env(text: str) -> str:
    def repl(m: re.Match[str]) -> str:
        name, default = m.group(1), m.group(2)
        value = os.environ.get(name)
        if value is None or value == "":
            if default is None:
                return ""
            return default
        return value

    return _ENV.sub(repl, text)


class PluginRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plugin: str = Field(description="Registered name, 'module:Class', or 'file.py:Class'.")
    options: dict[str, Any] = Field(default_factory=dict)


class SideEffect(str, Enum):
    READ = "read"  # returns information, changes nothing
    WRITE = "write"  # changes state in the world (booking, payment, cancellation)
    UI = "ui"  # returns an instruction for the client, not data


class ToolSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    side_effect: SideEffect = SideEffect.READ
    description: str | None = None


class MetricRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    threshold: float | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class ApplicationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    version: str | None = Field(default=None, description="Version/commit of the app under test.")
    connector: PluginRef
    adapter: PluginRef
    judge: PluginRef | None = None
    entry_agent: str | None = None
    tools: dict[str, ToolSpec] = Field(default_factory=dict)
    default_metrics: list[MetricRef] = Field(
        default_factory=list, description="Metrics run on every case, with or without expectations."
    )
    testcases: str | None = Field(default=None, description="Default test case path (relative).")
    base_dir: Path | None = Field(default=None, exclude=True)

    def write_tools(self) -> set[str]:
        return {n for n, s in self.tools.items() if s.side_effect == SideEffect.WRITE}

    def resolve_path(self, p: str | Path) -> Path:
        path = Path(p)
        if path.is_absolute() or self.base_dir is None:
            return path
        return (self.base_dir / path).resolve()


def load_application(path: str | Path) -> ApplicationConfig:
    p = Path(path)
    if p.is_dir():
        for candidate in ("app.yaml", "app.yml"):
            if (p / candidate).exists():
                p = p / candidate
                break
        else:
            raise FileNotFoundError(f"No app.yaml in {p}")
    data = yaml.safe_load(substitute_env(p.read_text(encoding="utf-8")))
    data = _default_metric_names(data)
    cfg = ApplicationConfig.model_validate(data)
    cfg.base_dir = p.parent.resolve()
    return cfg


def _default_metric_names(data: dict[str, Any]) -> dict[str, Any]:
    dm = data.get("default_metrics")
    if isinstance(dm, list):
        data["default_metrics"] = [{"name": x} if isinstance(x, str) else x for x in dm]
    return data
