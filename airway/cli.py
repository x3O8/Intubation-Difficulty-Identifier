from __future__ import annotations
import argparse, csv, json, html
from datetime import datetime, timezone
from pathlib import Path
from .db import initialize, transaction
from .video import decode_video, filename_timestamp, json_dump_strict, sha256_file, stable_video_uuid

def inventory(source, output, db_path="data/airway.sqlite3"):
    src=Path(source).resolve(); out=Path(output).resolve(); out.mkdir(parents=True,exist_ok=True); initialize(db_path)
    files=sorted(src.rglob("*.mp4"),key=lambda p:str(p.relative_to(src)).lower())
    prior={}
    progress=out/"decode_audit.jsonl"
    if progress.exists():
        for line in progress.read_text(encoding="utf-8").splitlines():
            try: prior[json.loads(line)["relative_path"]]=json.loads(line)
            except Exception: pass
    rows=[]
    for idx,p in enumerate(files,1):
        rel=p.relative_to(src).as_posix(); digest=sha256_file(p); vid=stable_video_uuid(rel,digest)
        old=prior.get(rel)
        if old and old.get("decoder_version")=="pyav-15.1-v1" and old.get("sha256")==digest and old.get("bytes")==p.stat().st_size: row=old
        else:
            meta=decode_video(p,contact_dir=out/"contact_frames",video_id=vid)
            row={"video_uuid":vid,"relative_path":rel,"source_path":str(p),"sha256":digest,"bytes":p.stat().st_size,
                 "untrusted_filename_timestamp":filename_timestamp(p.name),**meta,"participant_id":"","assignment_status":"unassigned","camera_view":"unknown","maneuver":"unknown"}
            with progress.open("a",encoding="utf-8") as f: f.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+"\n")
        rows.append(row)
        with transaction(db_path) as conn:
            conn.execute("INSERT INTO videos(id,source_path,relative_path,sha256,bytes,decode_status,metadata_json,created_at) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET decode_status=excluded.decode_status,metadata_json=excluded.metadata_json",
                         (vid,str(p),rel,digest,p.stat().st_size,row["status"],json.dumps(row,allow_nan=False),datetime.now(timezone.utc).isoformat()))
            exists=conn.execute("SELECT 1 FROM assignments WHERE video_id=? AND active=1",(vid,)).fetchone()
            if not exists:
                import uuid
                conn.execute("INSERT INTO assignments(id,video_id,status,camera_view,maneuver,created_at,active) VALUES(?,?,?,?,?,?,1)",(str(uuid.uuid4()),vid,"unassigned","unknown","unknown",datetime.now(timezone.utc).isoformat()))
        print(f"[{idx}/{len(files)}] {rel}: {row['status']}",flush=True)
    compact=[]
    for r in rows:
        x={k:v for k,v in r.items() if k!="presentation_timestamps_ms"}; x["pts_file"]=f"pts/{r['video_uuid']}.json"
        json_dump_strict(r.get("presentation_timestamps_ms",[]),out/x["pts_file"]); compact.append(x)
    json_dump_strict(compact,out/"inventory.json")
    fields=["video_uuid","relative_path","sha256","bytes","status","frame_count","duration_ms","width","height","codec","nominal_fps","average_fps","participant_id","assignment_status","camera_view","maneuver"]
    with (out/"inventory.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore"); w.writeheader(); w.writerows(compact)
    with (out/"unresolved_assignments.csv").open("w",newline="",encoding="utf-8-sig") as f:
        uf=["video_uuid","relative_path","participant_id","assignment_status","camera_view","maneuver"]
        w=csv.DictWriter(f,fieldnames=uf,extrasaction="ignore"); w.writeheader(); w.writerows([r for r in compact if r.get("assignment_status")!="confirmed"])
    cards=[]
    for r in compact:
        imgs="".join(f"<img loading='lazy' src='{html.escape(Path(c['path']).resolve().as_uri())}' alt='contact frame'>" for c in r.get("contact_frames",[]))
        cards.append(f"<article><h2>{html.escape(r['relative_path'])}</h2><code>{html.escape(r['video_uuid'])}</code><p>{html.escape(str(r.get('untrusted_filename_timestamp') or 'timestamp unavailable'))}</p><div>{imgs}</div><label>Camera view <input value='{html.escape(r.get('camera_view','unknown'))}'></label><label>Maneuver <input value='{html.escape(r.get('maneuver','unknown'))}'></label></article>")
    gallery="<!doctype html><meta charset='utf-8'><title>Airway inventory gallery</title><style>body{font:14px system-ui;max-width:1200px;margin:auto}article{border:1px solid #ccd6dd;padding:12px;margin:12px;border-radius:12px}img{width:30%;margin:1%;vertical-align:top}label{margin-right:15px}</style><h1>Local inventory review gallery</h1><p>Labels here are review aids only; import confirmed decisions through the application.</p>"+"".join(cards)
    (out/"gallery.html").write_text(gallery,encoding="utf-8")
    summary={"generated_at":datetime.now(timezone.utc).isoformat(),"source":str(src),"count":len(rows),"bytes":sum(r["bytes"] for r in rows),"statuses":{s:sum(r["status"]==s for r in rows) for s in ("success","partial","failed")}}
    json_dump_strict(summary,out/"summary.json"); return summary

def main(argv=None):
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="command",required=True)
    i=sub.add_parser("inventory"); i.add_argument("--source",required=True); i.add_argument("--output",required=True); i.add_argument("--db",default="data/airway.sqlite3")
    args=p.parse_args(argv)
    if args.command=="inventory": print(json.dumps(inventory(args.source,args.output,args.db),indent=2))
if __name__=="__main__": main()
