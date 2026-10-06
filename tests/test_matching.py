import pytest

from agentic_eval.core.matching import (
    ResolutionContext,
    UnresolvedReference,
    match_mapping,
    match_value,
    resolve,
)


def ctx(state=None, vars=None):
    return ResolutionContext(state=state or {}, vars=vars or {})


def test_whole_reference_keeps_type():
    assert resolve("{{ state.count }}", ctx({"count": 3})) == 3


def test_embedded_reference_is_text():
    assert resolve("flight {{ vars.f }} today", ctx(vars={"f": "FLT-1"})) == "flight FLT-1 today"


def test_nested_resolution():
    out = resolve({"a": ["{{ state.x }}", {"b": "{{ vars.y }}"}]}, ctx({"x": 1}, {"y": "z"}))
    assert out == {"a": [1, {"b": "z"}]}


def test_null_reference_is_unresolved():
    with pytest.raises(UnresolvedReference):
        resolve("{{ state.seat }}", ctx({"seat": None}))


@pytest.mark.parametrize("expected,actual,ok", [
    ({"$any": True}, "x", True),
    ({"$regex": "^[A-Z0-9]{6}$"}, "PGJ7CY", True),
    ({"$regex": "^[A-Z0-9]{6}$"}, "pgj7c", False),
    ({"$contains": "23A"}, "seat 23A", True),
    ({"$one_of": ["a", "b"]}, "b", True),
    ({"$ci": "23a"}, " 23A ", True),
    ({"$gte": 2}, 3, True),
    ({"$lte": 2}, 3, False),
    ("23", 23, True),
])
def test_matchers(expected, actual, ok):
    assert match_value(expected, actual)[0] is ok


def test_absent_matcher():
    assert match_value({"$absent": True}, None, present=False)[0]
    assert not match_value({"$absent": True}, 1, present=True)[0]


def test_match_mapping_subset_and_exact():
    ok, frac, _ = match_mapping({"a": 1}, {"a": 1, "b": 2})
    assert ok and frac == 1.0
    ok, frac, mm = match_mapping({"a": 1}, {"a": 1, "b": 2}, exact=True)
    assert not ok and "b" in mm and frac == 0.5
