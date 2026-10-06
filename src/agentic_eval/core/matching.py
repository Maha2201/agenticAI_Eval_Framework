"""Context references and value matchers.

Agentic apps generate values at runtime (booking references, ticket ids), so a
test case cannot hard-code them. Two mechanisms solve this:

1. **References**: ``{{ state.confirmation_number }}`` is replaced with a value
   from the conversation state before comparing (or before sending a user turn).
   Supported roots: ``state`` (state snapshot), ``vars`` (test case variables),
   ``env`` (environment variables).

2. **Matchers**: instead of a literal, an expectation value can be a one-key
   mapping that describes what is acceptable:

   ``{$any: true}``           any value, but the key must be present
   ``{$regex: "^[A-Z0-9]{6}$"}``  full regex match on the string form
   ``{$contains: "23A"}``     substring (strings) or membership (lists)
   ``{$one_of: [a, b]}``      equal to one of the listed values
   ``{$ci: "Seat 23A"}``      case-insensitive, whitespace-trimmed equality
   ``{$gte: 1}`` / ``{$lte: 5}``  numeric bounds
   ``{$absent: true}``        the key must NOT be present
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Mapping

_REF = re.compile(r"\{\{\s*([a-zA-Z_][\w]*)\.([\w.\-]+)\s*\}\}")
_WHOLE_REF = re.compile(r"^\s*\{\{\s*([a-zA-Z_][\w]*)\.([\w.\-]+)\s*\}\}\s*$")

MATCHER_KEYS = {"$any", "$regex", "$contains", "$one_of", "$ci", "$gte", "$lte", "$absent"}


class UnresolvedReference(KeyError):
    """A ``{{ root.path }}`` reference that the current context cannot satisfy."""


def _lookup(root: Mapping[str, Any], dotted: str) -> Any:
    current: Any = root
    for part in dotted.split("."):
        if isinstance(current, Mapping) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            raise UnresolvedReference(dotted)
    return current


@dataclass
class ResolutionContext:
    state: Mapping[str, Any]
    vars: Mapping[str, Any]

    def get(self, root: str, path: str) -> Any:
        if root == "state":
            value = _lookup(self.state, path)
        elif root == "vars":
            value = _lookup(self.vars, path)
        elif root == "env":
            if path not in os.environ:
                raise UnresolvedReference(f"env.{path}")
            value = os.environ[path]
        else:
            raise UnresolvedReference(f"{root}.{path}")
        if value is None:
            raise UnresolvedReference(f"{root}.{path} (value is null)")
        return value


def resolve(value: Any, ctx: ResolutionContext) -> Any:
    """Recursively replace ``{{ root.path }}`` references.

    A string that is *only* a reference keeps the referenced value's type
    (so ``"{{ state.count }}"`` can resolve to an int). References embedded in
    a longer string are substituted as text.
    """
    if isinstance(value, str):
        whole = _WHOLE_REF.match(value)
        if whole:
            return ctx.get(whole.group(1), whole.group(2))
        return _REF.sub(lambda m: str(ctx.get(m.group(1), m.group(2))), value)
    if isinstance(value, list):
        return [resolve(v, ctx) for v in value]
    if isinstance(value, Mapping):
        return {k: resolve(v, ctx) for k, v in value.items()}
    return value


def has_reference(value: Any) -> bool:
    if isinstance(value, str):
        return bool(_REF.search(value))
    if isinstance(value, list):
        return any(has_reference(v) for v in value)
    if isinstance(value, Mapping):
        return any(has_reference(v) for v in value.values())
    return False


def is_matcher(value: Any) -> bool:
    return isinstance(value, Mapping) and len(value) == 1 and next(iter(value)) in MATCHER_KEYS


def contains_matcher(value: Any) -> bool:
    if is_matcher(value):
        return True
    if isinstance(value, list):
        return any(contains_matcher(v) for v in value)
    if isinstance(value, Mapping):
        return any(contains_matcher(v) for v in value.values())
    return False


def _equal(expected: Any, actual: Any) -> bool:
    if expected == actual:
        return True
    # Tolerate "23" vs 23 style differences that come from JSON-string arguments.
    if isinstance(expected, (int, float, str)) and isinstance(actual, (int, float, str)):
        return str(expected) == str(actual)
    return False


def match_value(expected: Any, actual: Any, *, present: bool = True) -> tuple[bool, str]:
    """Compare one expected value (literal or matcher) with an actual value."""
    if is_matcher(expected):
        op, arg = next(iter(expected.items()))
        if op == "$absent":
            ok = (not present) if arg else present
            return ok, "key absent" if ok else "key present but should be absent"
        if not present:
            return False, "key missing"
        if op == "$any":
            return True, "present"
        if op == "$regex":
            ok = re.fullmatch(str(arg), str(actual)) is not None
            return ok, f"regex {'matched' if ok else 'did not match'} {arg!r}"
        if op == "$contains":
            if isinstance(actual, (list, tuple, set)):
                ok = arg in actual
            else:
                ok = str(arg) in str(actual)
            return ok, f"{'contains' if ok else 'does not contain'} {arg!r}"
        if op == "$one_of":
            ok = any(_equal(a, actual) for a in arg)
            return ok, f"{actual!r} {'in' if ok else 'not in'} {arg!r}"
        if op == "$ci":
            ok = str(arg).strip().casefold() == str(actual).strip().casefold()
            return ok, "case-insensitive match" if ok else f"{actual!r} != {arg!r} (ci)"
        if op in ("$gte", "$lte"):
            try:
                a, b = float(actual), float(arg)
            except (TypeError, ValueError):
                return False, f"{actual!r} is not numeric"
            ok = a >= b if op == "$gte" else a <= b
            return ok, f"{actual!r} {op[1:]} {arg!r}: {ok}"
    if not present:
        return False, "key missing"
    if isinstance(expected, Mapping) and isinstance(actual, Mapping):
        ok, _, mismatches = match_mapping(expected, actual)
        return ok, "nested match" if ok else f"nested mismatch: {mismatches}"
    ok = _equal(expected, actual)
    return ok, "equal" if ok else f"expected {expected!r}, got {actual!r}"


def match_mapping(
    expected: Mapping[str, Any], actual: Mapping[str, Any], *, exact: bool = False
) -> tuple[bool, float, dict[str, str]]:
    """Match expected keys against an actual mapping.

    Returns ``(all_matched, fraction_matched, mismatches)``. With ``exact``,
    keys present in ``actual`` but not in ``expected`` count as mismatches.
    """
    if not expected and not exact:
        return True, 1.0, {}
    mismatches: dict[str, str] = {}
    matched = 0
    for key, exp in expected.items():
        ok, why = match_value(exp, actual.get(key), present=key in actual)
        if ok:
            matched += 1
        else:
            mismatches[key] = why
    total = len(expected)
    if exact:
        extra = [k for k in actual if k not in expected]
        for k in extra:
            mismatches[k] = "unexpected key"
        total += len(extra)
    fraction = matched / total if total else 1.0
    return not mismatches, fraction, mismatches
