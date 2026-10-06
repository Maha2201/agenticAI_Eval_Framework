"""Plugin registry.

A plugin is referenced in config in one of three ways:

* a registered name:            ``http``, ``agent_path``, ``deepeval``
* an importable class path:     ``my_package.adapters:MyAdapter``
* a file next to the config:    ``adapter.py:MyAdapter``

Built-in plugins register themselves with the decorators below. External
packages can register through the ``agentic_eval.plugins`` entry point group:
the entry point's module is imported, and its decorators do the rest.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import sys
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any, Callable, Literal, TypeVar

Kind = Literal["connector", "adapter", "metric", "judge"]
KINDS: tuple[Kind, ...] = ("connector", "adapter", "metric", "judge")

T = TypeVar("T", bound=type)

_REGISTRY: dict[str, dict[str, type]] = {k: {} for k in KINDS}
_BUILTINS_LOADED = False
_ENTRY_POINTS_LOADED = False


class PluginError(LookupError):
    pass


def register(kind: Kind, name: str | None = None) -> Callable[[T], T]:
    def decorator(cls: T) -> T:
        key = name or getattr(cls, "name", None) or cls.__name__
        existing = _REGISTRY[kind].get(key)
        if existing is not None and existing is not cls:
            raise PluginError(f"{kind} {key!r} already registered by {existing.__module__}")
        _REGISTRY[kind][key] = cls
        return cls

    return decorator


def register_connector(name: str | None = None) -> Callable[[T], T]:
    return register("connector", name)


def register_adapter(name: str | None = None) -> Callable[[T], T]:
    return register("adapter", name)


def register_metric(name: str | None = None) -> Callable[[T], T]:
    return register("metric", name)


def register_judge(name: str | None = None) -> Callable[[T], T]:
    return register("judge", name)


def _load_builtins() -> None:
    global _BUILTINS_LOADED
    if _BUILTINS_LOADED:
        return
    _BUILTINS_LOADED = True
    # Importing these modules runs their @register decorators.
    for module in (
        "agentic_eval.connectors.http",
        "agentic_eval.connectors.replay",
        "agentic_eval.metrics.trajectory",
        "agentic_eval.metrics.tools",
        "agentic_eval.metrics.state",
        "agentic_eval.metrics.safety",
        "agentic_eval.metrics.operational",
        "agentic_eval.metrics.deepeval_metrics",
        "agentic_eval.metrics.rubric",
        "agentic_eval.judges.deepeval_judge",
    ):
        importlib.import_module(module)


def _load_entry_points() -> None:
    global _ENTRY_POINTS_LOADED
    if _ENTRY_POINTS_LOADED:
        return
    _ENTRY_POINTS_LOADED = True
    for ep in entry_points(group="agentic_eval.plugins"):
        ep.load()


def _load_from_file(file_part: str, attr: str, base_dir: Path | None) -> type:
    path = Path(file_part)
    if not path.is_absolute():
        path = (base_dir or Path.cwd()) / path
    path = path.resolve()
    if not path.exists():
        raise PluginError(f"Plugin file not found: {path}")
    digest = hashlib.sha1(str(path).encode()).hexdigest()[:10]
    module_name = f"agentic_eval_plugin_{path.stem}_{digest}"
    module = sys.modules.get(module_name)
    if module is None:
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise PluginError(f"Cannot import {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    try:
        return getattr(module, attr)
    except AttributeError as exc:
        raise PluginError(f"{path} has no attribute {attr!r}") from exc


def resolve(kind: Kind, ref: str, *, base_dir: Path | None = None) -> type:
    """Turn a config reference into a plugin class."""
    _load_builtins()
    if ref in _REGISTRY[kind]:
        return _REGISTRY[kind][ref]
    if ":" in ref:
        left, attr = ref.rsplit(":", 1)
        if left.endswith(".py") or "/" in left or "\\" in left:
            return _load_from_file(left, attr, base_dir)
        try:
            module = importlib.import_module(left)
        except ImportError as exc:
            raise PluginError(f"Cannot import {left!r} for {kind} {ref!r}: {exc}") from exc
        try:
            return getattr(module, attr)
        except AttributeError as exc:
            raise PluginError(f"{left!r} has no attribute {attr!r}") from exc
    _load_entry_points()
    if ref in _REGISTRY[kind]:
        return _REGISTRY[kind][ref]
    known = ", ".join(sorted(_REGISTRY[kind])) or "none"
    raise PluginError(f"Unknown {kind} {ref!r}. Registered: {known}")


def create(kind: Kind, ref: str, *, base_dir: Path | None = None, **kwargs: Any) -> Any:
    return resolve(kind, ref, base_dir=base_dir)(**kwargs)


def available(kind: Kind | None = None) -> dict[str, list[str]]:
    _load_builtins()
    _load_entry_points()
    kinds = [kind] if kind else list(KINDS)
    return {k: sorted(_REGISTRY[k]) for k in kinds}
