"""P3 provenance gate — extract-and-match logic and orchestrator wiring."""
from backend.app import provenance


def test_grounded_numbers_pass():
    tool_results = [{"overall_pct": 82.3, "subjects": [
        {"subject": "18CS51", "attended": 40, "held": 48}]}]
    text = "Your overall attendance is 82.3%. You attended 40 of 48 classes."
    r = provenance.check(text, tool_results)
    assert r["ungrounded"] == []
    assert not r["blocked"]


def test_fabricated_number_is_blocked():
    tool_results = [{"overall_pct": 82.3}]
    text = "Your overall attendance is 95%."
    r = provenance.check(text, tool_results)
    assert r["ungrounded"] == [95.0]
    assert r["blocked"]


def test_static_institutional_constants_are_grounded():
    text = "That is below the 75% requirement."
    r = provenance.check(text, [{"overall_pct": 40.0}])
    assert r["ungrounded"] == []


def test_no_tools_called_yields_no_claims():
    r = provenance.check("Hello! How can I help you today?", [])
    assert r["claims_checked"] == 0
    assert not r["blocked"]


def test_rounding_within_tolerance_is_not_blocked():
    r = provenance.check("about 82.32%", [{"overall_pct": 82.30}])
    assert not r["blocked"]


def test_orchestrator_gate_falls_back_when_blocked(agents):
    orch = agents["orchestrator_agent"]
    tools_used = [{"name": "get_attendance", "args": {}, "ms": 1.0}]
    tool_results = [{"usn": "X", "overall_pct": 60.0, "subjects": []}]
    gate = orch._gate("Your attendance is 99%, well above requirement.",
                      tools_used, tool_results)
    assert gate["blocked"]
    assert gate["fell_back"]
    assert "99" not in gate["text"]


def test_orchestrator_gate_leaves_grounded_text_untouched(agents):
    orch = agents["orchestrator_agent"]
    tools_used = [{"name": "get_attendance", "args": {}, "ms": 1.0}]
    tool_results = [{"usn": "X", "overall_pct": 60.0, "subjects": []}]
    text = "Your attendance is 60.0%."
    gate = orch._gate(text, tools_used, tool_results)
    assert not gate["blocked"]
    assert gate["text"] == text


def test_orchestrator_gate_skips_when_no_tools_called(agents):
    orch = agents["orchestrator_agent"]
    assert orch._gate("Hi there!", [], []) is None
