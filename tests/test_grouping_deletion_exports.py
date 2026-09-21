import json, uuid
from pathlib import Path
import pytest
from airway.db import initialize, transaction
from airway.ingest import import_mapping, ensure_under_managed, propose_sequential_triplets
from airway import LIMITATION

def seed(db):
    initialize(db)
    with transaction(db) as c:
        c.execute("INSERT INTO videos(id,source_path,relative_path,sha256,bytes,created_at) VALUES('v1','X:/source/a.mp4','a.mp4','abc',1,'now')")
        c.execute("INSERT INTO assignments(id,video_id,status,created_at,active) VALUES('a1','v1','unassigned','now',1)")

def test_import_never_auto_confirms(tmp_path):
    db=tmp_path/"x.sqlite3"; seed(db); p=tmp_path/"m.csv"
    p.write_text("relative_path,participant_id,assignment_status\na.mp4,P0001,provisional\n",encoding="utf-8")
    import_mapping(p,db)
    with transaction(db) as c: assert c.execute("SELECT status FROM assignments WHERE active=1").fetchone()[0]=="provisional"

def test_confirmed_requires_participant(tmp_path):
    db=tmp_path/"x.sqlite3"; seed(db); p=tmp_path/"m.csv"
    p.write_text("relative_path,participant_id,assignment_status\na.mp4,,confirmed\n",encoding="utf-8")
    with pytest.raises(ValueError): import_mapping(p,db)

def test_path_escape_refused(tmp_path):
    root=tmp_path/"managed"; root.mkdir()
    with pytest.raises(ValueError): ensure_under_managed(tmp_path/"outside",root)

def test_fixed_limitation(): assert LIMITATION=="Insufficient evidence to estimate overall intubation difficulty."

def test_owner_declared_triplets_stay_provisional(tmp_path):
    db=tmp_path/"x.sqlite3"; initialize(db)
    with transaction(db) as c:
        for i in range(3):
            c.execute("INSERT INTO videos(id,source_path,relative_path,sha256,bytes,created_at) VALUES(?,?,?,?,?,?)",(f"v{i}",f"x/{i}.mp4",f"{i}.mp4","x",1,"now"))
            c.execute("INSERT INTO assignments(id,video_id,status,created_at,active) VALUES(?,?,?,?,1)",(f"a{i}",f"v{i}","unassigned","now"))
    result=propose_sequential_triplets(db)
    assert result["patients"]==1
    with transaction(db) as c:
        assert c.execute("SELECT COUNT(*) FROM assignments WHERE active=1 AND status='provisional'").fetchone()[0]==3
