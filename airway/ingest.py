from __future__ import annotations
import csv, json, shutil, uuid
from datetime import datetime, timezone
from pathlib import Path
from .db import transaction
from .video import sha256_file

STATUSES={"unassigned","provisional","confirmed","disputed"}
VIEWS={"front","lateral","unknown","mixed","unsupported"}

def now(): return datetime.now(timezone.utc).isoformat()

def import_mapping(csv_path, db_path="data/airway.sqlite3", reviewer="reviewer"):
    made=[]
    with open(csv_path,newline="",encoding="utf-8-sig") as f, transaction(db_path) as conn:
        for row in csv.DictReader(f):
            status=row.get("assignment_status","unassigned").strip() or "unassigned"
            if status not in STATUSES: raise ValueError(f"invalid status {status}")
            vid=row.get("video_uuid")
            if not vid and row.get("relative_path"):
                found=conn.execute("SELECT id FROM videos WHERE relative_path=?",(row["relative_path"],)).fetchone(); vid=found[0] if found else None
            if not vid: raise ValueError("mapping row does not match an inventoried video")
            pid=(row.get("participant_id") or "").strip() or None
            if status=="confirmed" and not pid: raise ValueError("confirmed mapping requires participant_id")
            if pid: conn.execute("INSERT OR IGNORE INTO participants VALUES(?,?,?,NULL)",(pid,status,now()))
            conn.execute("UPDATE assignments SET active=0 WHERE video_id=? AND active=1",(vid,))
            aid=str(uuid.uuid4())
            conn.execute("INSERT INTO assignments(id,video_id,participant_id,status,camera_view,maneuver,side,source,reviewer,created_at,active) VALUES(?,?,?,?,?,?,?,?,?,?,1)",
                         (aid,vid,pid,status,row.get("camera_view","unknown") or "unknown",row.get("maneuver","unknown") or "unknown",row.get("side"),str(csv_path),reviewer,now()))
            made.append(aid)
    return made

def propose_sequential_triplets(db_path="data/airway.sqlite3", reviewer="owner_provisional_grouping"):
    """Assign adjacent inventoried clips into provisional triads.

    This uses only the owner's declared dataset ordering; it never compares
    faces or claims that the three clips identify the same person.
    """
    made=[]
    with transaction(db_path) as conn:
        clips=conn.execute("SELECT v.id FROM videos v JOIN assignments a ON a.video_id=v.id AND a.active=1 WHERE a.status='unassigned' ORDER BY v.relative_path").fetchall()
        complete_count=len(clips)//3*3
        start=conn.execute("SELECT COUNT(*) FROM participants").fetchone()[0]
        for offset in range(0,complete_count,3):
            pid=f"PROVISIONAL-{start + offset//3 + 1:04d}"
            conn.execute("INSERT INTO participants VALUES(?,?,?,NULL)",(pid,"provisional",now()))
            for video in clips[offset:offset+3]:
                conn.execute("UPDATE assignments SET active=0 WHERE video_id=? AND active=1",(video["id"],))
                aid=str(uuid.uuid4())
                conn.execute("INSERT INTO assignments(id,video_id,participant_id,status,camera_view,maneuver,source,reviewer,created_at,active) VALUES(?,?,?,?,?,?,?,?,?,1)",
                             (aid,video["id"],pid,"provisional","unknown","unknown","owner_declared_adjacent_triplet",reviewer,now()))
                made.append(aid)
    return {"patients":complete_count//3,"assignments":len(made),"remainder_unassigned":len(clips)-complete_count,"status":"provisional"}

def materialize_confirmed(participant_id, db_path="data/airway.sqlite3", managed_root="data/participants"):
    root=Path(managed_root).resolve(); dest=(root/participant_id).resolve()
    if root not in dest.parents: raise ValueError("managed path escape refused")
    with transaction(db_path) as conn:
        rows=conn.execute("SELECT v.*,a.camera_view,a.maneuver FROM videos v JOIN assignments a ON a.video_id=v.id WHERE a.participant_id=? AND a.status='confirmed' AND a.active=1",(participant_id,)).fetchall()
    manifest={"participant_id":participant_id,"status":"confirmed","videos":[]}
    for row in rows:
        src=Path(row["source_path"]); out=dest/"originals"/row["id"]/src.name
        out.parent.mkdir(parents=True,exist_ok=True)
        if not out.exists() or sha256_file(out)!=row["sha256"]:
            tmp=out.with_suffix(out.suffix+".tmp"); shutil.copy2(src,tmp)
            if sha256_file(tmp)!=row["sha256"]: tmp.unlink(missing_ok=True); raise IOError("copied hash mismatch")
            tmp.replace(out)
        manifest["videos"].append({"video_uuid":row["id"],"name":src.name,"sha256":row["sha256"],"camera_view":row["camera_view"],"maneuver":row["maneuver"]})
    (dest/"participant_manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    return manifest

def ensure_under_managed(path, managed_root="data"):
    root=Path(managed_root).resolve(); p=Path(path).resolve()
    if p==root or root not in p.parents: raise ValueError("refusing path outside managed root")
    return p

def delete_case(case_id, db_path="data/airway.sqlite3", managed_root="data"):
    with transaction(db_path) as conn:
        row=conn.execute("SELECT participant_id FROM cases WHERE id=? AND deleted_at IS NULL",(case_id,)).fetchone()
        if not row: return False
        p=ensure_under_managed(Path(managed_root)/"participants"/(row[0] or "unassigned")/"cases"/case_id,managed_root)
        conn.execute("UPDATE cases SET deleted_at=?,status='deleted' WHERE id=?",(now(),case_id)); conn.execute("DELETE FROM cases WHERE id=?",(case_id,))
    if p.exists(): shutil.rmtree(p)
    return True
