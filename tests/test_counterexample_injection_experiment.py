from scripts.run_counterexample_injection_experiment import run_experiment


def test_frozen_cross_domain_protocol_selftest_has_no_missed_or_extra_alarms():
    result = run_experiment()
    summary = result["summary"]

    assert summary["cases"] == 14
    assert summary["injected"] == 7
    assert summary["detected"] == 7
    assert summary["injected_recall"] == 1.0
    assert summary["controls"] == 7
    assert summary["false_alarms"] == 0
    assert summary["control_false_alarm_rate"] == 0.0
    assert result["per_family"]["code"]["detected"] == 2
    assert result["per_family"]["table"]["detected"] == 1
    assert result["per_family"]["workspace"]["detected"] == 3
    assert result["per_family"]["open_ended"]["detected"] == 1
