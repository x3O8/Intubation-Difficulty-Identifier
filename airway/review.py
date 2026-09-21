from __future__ import annotations
import json, uuid
from .db import transaction
from .ingest import now

def save_revision(case_id, reviewer, payload, proposal_id=None, supersedes_id=None, db_path="data/airway.sqlite3"):
    rid=str(uuid.uuid4())
    with transaction(db_path) as conn:
        conn.execute("INSERT INTO review_revisions VALUES(?,?,?,?,?,?,?,?)",(rid,case_id,proposal_id,reviewer,json.dumps(payload,allow_nan=False),payload.get("state","needs_review"),now(),supersedes_id))
        metric_id=payload.get("metric_id")
        conn.execute("UPDATE measurements SET active=0 WHERE case_id=? AND metric_id=? AND active=1",(case_id,metric_id))
        endpoints=payload.get("endpoints") or []
        value=None; unit=None
        if len(endpoints)==2 and payload.get("state")=="available":
            from .measurements import distance
            value=distance(endpoints[0],endpoints[1]); unit="px"
        conn.execute("""INSERT INTO measurements(id,case_id,metric_id,metric_version,timestamp_ms,value,unit,coordinate_space,method,endpoints_json,state,reason_codes_json,review_revision_id,reviewer,revised_at,active)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
                     (str(uuid.uuid4()),case_id,metric_id,"1.0",payload.get("neutral_timestamp_ms"),value,unit,payload.get("coordinate_space"),"human_review",json.dumps(endpoints,allow_nan=False),payload.get("state","needs_review"),json.dumps([payload.get("reason")] if payload.get("reason") else []),rid,reviewer,now()))
        conn.execute("UPDATE report_snapshots SET invalidated_at=? WHERE case_id=? AND invalidated_at IS NULL",(now(),case_id))
    return rid

def latest_case_revision(case_id, db_path="data/airway.sqlite3"):
    with transaction(db_path) as conn:
        r=conn.execute("SELECT * FROM review_revisions WHERE case_id=? ORDER BY created_at DESC LIMIT 1",(case_id,)).fetchone()
        return dict(r) if r else None
