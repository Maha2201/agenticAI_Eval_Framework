"""Command line interface.

    agentic-eval run       APP [--cases PATH] [--record DIR | --replay DIR] [--no-judge] ...
    agentic-eval validate  APP [--cases PATH]
    agentic-eval trace     APP --case ID --replay DIR
    agentic-eval plugins

APP is an application folder (containing app.yaml) or the app.yaml path.
Exit codes for `run`: 0 all passed, 1 harness error, 2 threshold breach.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from agentic_eval import __version__
from agentic_eval.core import registry
from agentic_eval.core.config import load_application
from agentic_eval.core.runner import RunOptions, Runner
from agentic_eval.core.testcase import load_test_cases
from agentic_eval.reporting import console_line, console_summary, write_json, write_markdown


def _load_dotenv() -> None:
    """Minimal .env support (KEY=VALUE lines) so no extra dependency is needed."""
    import os

    env = Path.cwd() / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _cases_path(app, arg: str | None) -> Path:
    if arg:
        return Path(arg)
    if app.testcases:
        return app.resolve_path(app.testcases)
    raise SystemExit("No test cases given: pass --cases or set 'testcases' in app.yaml")


def cmd_run(args: argparse.Namespace) -> int:
    app = load_application(args.app)
    cases = load_test_cases(_cases_path(app, args.cases))
    opts = RunOptions(
        record_dir=Path(args.record) if args.record else None,
        replay_dir=Path(args.replay) if args.replay else None,
        use_judge=not args.no_judge,
        include_tags=set(args.tag or []),
        exclude_tags=set(args.skip_tag or []),
        case_ids=set(args.case or []),
        keep_raw=args.keep_raw,
    )
    if opts.record_dir and opts.replay_dir:
        raise SystemExit("--record and --replay are mutually exclusive")
    mode = "replay" if opts.replay_dir else ("live+record" if opts.record_dir else "live")
    print(f"agentic-eval {__version__} | app={app.name} | mode={mode} | "
          f"judge={'off' if not opts.use_judge or not app.judge else app.judge.plugin}")
    runner = Runner(app, opts)
    run = runner.run(cases, on_result=lambda r: print(console_line(r)))
    out = Path(args.out) / f"{app.name}_{datetime.now():%Y%m%d_%H%M%S}_{run.run_id}"
    write_json(run, out / "run.json")
    write_markdown(run, out / "report.md")
    print(console_summary(run))
    print(f"Reports: {out}")
    return run.exit_code


def cmd_validate(args: argparse.Namespace) -> int:
    app = load_application(args.app)
    print(f"app.yaml OK: {app.name}")
    for kind, ref in (("connector", app.connector), ("adapter", app.adapter), ("judge", app.judge)):
        if ref is not None:
            cls = registry.resolve(kind, ref.plugin, base_dir=app.base_dir)
            print(f"  {kind:9} {ref.plugin} -> {cls.__module__}.{cls.__name__}")
    for m in app.default_metrics:
        registry.resolve("metric", m.name, base_dir=app.base_dir)
    cases = load_test_cases(_cases_path(app, args.cases))
    print(f"{len(cases)} test case(s) valid")
    for c in cases:
        rub = c.expectations.rubric
        if rub is not None and not rub.evaluation_steps:
            print(f"  warning: {c.id}: rubric has no evaluation_steps; the judge will write "
                  "its own, which can drift from the criteria")
    return 0


def cmd_trace(args: argparse.Namespace) -> int:
    app = load_application(args.app)
    cases = [c for c in load_test_cases(_cases_path(app, args.cases)) if c.id == args.case]
    if not cases:
        raise SystemExit(f"No test case {args.case!r}")
    runner = Runner(app, RunOptions(replay_dir=Path(args.replay) if args.replay else None,
                                    use_judge=False, keep_raw=args.keep_raw))
    trace = runner.execute_conversation(cases[0])
    print(trace.model_dump_json(indent=2, exclude_none=True))
    return 0


def cmd_plugins(args: argparse.Namespace) -> int:
    for kind, names in registry.available().items():
        print(f"{kind}s: {', '.join(names) or '(none)'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agentic-eval", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("run", help="run a test suite")
    r.add_argument("app")
    r.add_argument("--cases")
    r.add_argument("--record", metavar="DIR", help="save raw responses while running live")
    r.add_argument("--replay", metavar="DIR", help="run from saved responses (offline)")
    r.add_argument("--no-judge", action="store_true", help="skip LLM-judged metrics")
    r.add_argument("--tag", action="append", help="only cases with this tag (repeatable)")
    r.add_argument("--skip-tag", action="append", help="skip cases with this tag (repeatable)")
    r.add_argument("--case", action="append", help="only this case id (repeatable)")
    r.add_argument("--out", default="reports")
    r.add_argument("--keep-raw", action="store_true", help="include raw responses in run.json")
    r.set_defaults(func=cmd_run)

    v = sub.add_parser("validate", help="check config, plugins and test cases load")
    v.add_argument("app")
    v.add_argument("--cases")
    v.set_defaults(func=cmd_validate)

    t = sub.add_parser("trace", help="print the normalised trace for one case")
    t.add_argument("app")
    t.add_argument("--case", required=True)
    t.add_argument("--cases")
    t.add_argument("--replay", metavar="DIR")
    t.add_argument("--keep-raw", action="store_true")
    t.set_defaults(func=cmd_trace)

    pl = sub.add_parser("plugins", help="list registered plugins")
    pl.set_defaults(func=cmd_plugins)
    return p


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    try:
        return int(args.func(args))
    except SystemExit:
        raise
    except Exception as exc:  # harness error
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
