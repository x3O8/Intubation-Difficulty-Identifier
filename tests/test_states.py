import json, sqlite3
import pytest
from airway.quality import evidence_state
from airway.measurements import json_number
from airway.db import initialize, connect

@pytest.mark.parametrize("kwargs,reason",[
 ({"maneuver":False},"missing_maneuver"),({"anatomy":False},"anatomy_not_visible"),
 ({"calibration":False},"missing_calibration"),({"multiple_faces":True},"multiple_faces"),({"readable":False},"unreadable_media")])
def test_missing_evidence_explicit(kwargs,reason):
    state,reasons=evidence_state(**kwargs); assert state=="unavailable" and reason in reasons

def test_non_finite_json_rejected():
    with pytest.raises(ValueError): json_number(float("nan"))

def test_foreign_keys_enabled(tmp_path):
    p=tmp_path/"x.sqlite3"; initialize(p)
    with connect(p) as c: assert c.execute("PRAGMA foreign_keys").fetchone()[0]==1
