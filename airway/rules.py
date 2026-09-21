from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class Rule:
    id: str; metric_id: str; unit: str; comparator: str; threshold: float; outcome: str; kind: str; active: bool = True

def compare(value, comparator, threshold):
    if value is None: return False
    return {"<": value < threshold, ">": value > threshold, "<=": value <= threshold, ">=": value >= threshold}[comparator]

def evaluate(measurement: dict, rule: Rule, *, accepted=False, protocol_match=False, anatomy_ok=False, calibration_ok=False):
    gates = [
        (accepted and measurement.get("state") == "available", "accepted_review_required"),
        (protocol_match, "protocol_mismatch"),
        (anatomy_ok, "anatomy_or_quality_unsupported"),
        (measurement.get("unit") == rule.unit, "unsupported_unit"),
        (calibration_ok if rule.unit == "cm" else True, "missing_calibration"),
        (rule.active, "inactive_rule"),
    ]
    for ok, reason in gates:
        if not ok: return {"eligible": False, "matched": False, "reason": reason}
    return {"eligible": True, "matched": compare(measurement.get("value"), rule.comparator, rule.threshold), "reason": None}

INTERINCISOR_LT3 = Rule("interincisor_lt3_dl_v1","interincisor_opening","cm","<",3.0,"difficult_laryngoscopy","adverse_indicator")
INTERINCISOR_GT5 = Rule("interincisor_gt5_normal_v1","interincisor_opening","cm",">",5.0,"normal_reference","normal_reference")
LMA_LT2 = Rule("opening_lt2_lma_v1","interincisor_opening","cm","<",2.0,"difficult_supraglottic_device_insertion","adverse_indicator")
