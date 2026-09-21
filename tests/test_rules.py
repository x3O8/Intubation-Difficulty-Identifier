import pytest
from airway.rules import evaluate, INTERINCISOR_LT3, INTERINCISOR_GT5, LMA_LT2

def ok(value, rule):
    return evaluate({"state":"available","unit":"cm","value":value},rule,accepted=True,protocol_match=True,anatomy_ok=True,calibration_ok=True)

def test_exact_boundaries():
    assert ok(2.99,INTERINCISOR_LT3)["matched"]
    assert not ok(3.00,INTERINCISOR_LT3)["matched"]
    assert not ok(5.00,INTERINCISOR_GT5)["matched"]
    assert ok(5.01,INTERINCISOR_GT5)["matched"]
    assert not ok(None,INTERINCISOR_LT3)["matched"]

def test_pixels_cannot_enter_cm_rule():
    r=evaluate({"state":"available","unit":"px","value":2},INTERINCISOR_LT3,accepted=True,protocol_match=True,anatomy_ok=True,calibration_ok=False)
    assert not r["eligible"] and r["reason"]=="unsupported_unit"

def test_lma_outcome_is_not_intubation():
    assert LMA_LT2.outcome=="difficult_supraglottic_device_insertion"
    assert "intubation" not in LMA_LT2.outcome
