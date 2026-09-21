from __future__ import annotations
import csv, hashlib, html, io, json, uuid
from pathlib import Path
from . import LIMITATION
from .aggregate import summarize_case_measurements
from .db import transaction
from .ingest import now, ensure_under_managed

def _safe_csv(value):
    if value is None: return ""
    s=str(value)
    return "'"+s if s[:1] in ("=","+","-","@") else s

def build_payload(case_id, db_path="data/airway.sqlite3"):
    with transaction(db_path) as conn:
        case=conn.execute("SELECT * FROM cases WHERE id=?",(case_id,)).fetchone()
        if not case: raise ValueError("case not found")
        ms=[dict(x) for x in conn.execute("SELECT * FROM measurements WHERE case_id=? AND active=1 ORDER BY metric_id",(case_id,))]
        for m in ms:
            for key in ("interval_json","endpoints_json","quality_json","reason_codes_json"):
                m[key[:-5] if key.endswith("_json") else key]=json.loads(m.pop(key) or "null")
        vids=[dict(x) for x in conn.execute("SELECT DISTINCT v.id,v.relative_path,v.sha256 FROM videos v JOIN measurements m ON m.video_id=v.id WHERE m.case_id=?",(case_id,))]
    summary=summarize_case_measurements(ms,[v["id"] for v in vids])
    return {"schema_version":"1.0","case":dict(case),"videos":vids,"measurements":ms,"cross_video_evidence_summary":summary,"conclusion":LIMITATION}

def export_case(case_id, out_dir, db_path="data/airway.sqlite3"):
    out=ensure_under_managed(out_dir,"data"); out.mkdir(parents=True,exist_ok=True)
    payload=build_payload(case_id,db_path); canonical=json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)
    digest=hashlib.sha256(canonical.encode()).hexdigest()
    json_path=out/f"report-{digest[:12]}.json"; json_path.write_text(json.dumps(payload,indent=2,ensure_ascii=False,allow_nan=False),encoding="utf-8")
    fields=["metric_id","state","value","unit","timestamp_ms","method","reason_codes","source_hash","reviewer","revised_at"]
    csv_path=out/f"report-{digest[:12]}.csv"
    with csv_path.open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
        for m in payload["measurements"]: w.writerow({k:_safe_csv(json.dumps(m.get(k)) if isinstance(m.get(k),(list,dict)) else m.get(k)) for k in fields})
    frame_csv_path=out/f"frames-{digest[:12]}.csv"
    with transaction(db_path) as conn:
        artifacts=[dict(x) for x in conn.execute("SELECT a.path,r.id run_id FROM analysis_artifacts a JOIN analysis_runs r ON r.id=a.run_id WHERE r.case_id=? AND a.kind='per_frame_json' AND r.state='completed'",(case_id,))]
    frame_fields=["run_id","timestamp_ms","face_count","valid","reason_codes","visible_lip_aperture_px","mouth_width_px","lip_aperture_over_mouth_width","lip_aperture_over_outer_eye_span"]
    with frame_csv_path.open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=frame_fields); w.writeheader()
        for artifact in artifacts:
            raw=json.loads(Path(artifact["path"]).read_text(encoding="utf-8"))
            for frame in raw.get("frames",[]):
                row={k:frame.get(k) for k in frame_fields}; row["run_id"]=artifact["run_id"]; row["reason_codes"]=json.dumps(frame.get("reason_codes") or [])
                w.writerow({k:_safe_csv(v) for k,v in row.items()})
    rows="".join(f"<tr><td>{html.escape(str(m['metric_id']))}</td><td>{html.escape(str(m['state']))}</td><td>{html.escape(str(m.get('value') if m.get('value') is not None else ''))}</td><td>{html.escape(str(m.get('unit') or ''))}</td><td>{html.escape(', '.join(m.get('reason_codes') or []))}</td></tr>" for m in payload["measurements"])
    doc=f"""<!doctype html><html><head><meta charset='utf-8'><title>Airway evidence report</title><style>body{{font:15px system-ui;max-width:960px;margin:40px auto;color:#17202a}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ccd6dd;padding:8px;text-align:left}}.limit{{background:#fff3cd;padding:16px;border-left:5px solid #b7791f}}@media print{{body{{margin:12mm}}}}</style></head><body><h1>Airway video evidence report</h1><p>Case {html.escape(case_id)}</p><div class='limit'><strong>{html.escape(LIMITATION)}</strong></div><h2>Measurements</h2><table><thead><tr><th>Metric</th><th>State</th><th>Value</th><th>Unit</th><th>Reasons</th></tr></thead><tbody>{rows}</tbody></table><p>Snapshot SHA-256: {digest}</p></body></html>"""
    html_path=out/f"report-{digest[:12]}.html"; html_path.write_text(doc,encoding="utf-8")
    with transaction(db_path) as conn:
        conn.execute("INSERT INTO report_snapshots VALUES(?,?,?,?,?,?,NULL)",(str(uuid.uuid4()),case_id,None,digest,canonical,now()))
    return {"html":html_path,"json":json_path,"csv":csv_path,"frames_csv":frame_csv_path,"snapshot_hash":digest}
