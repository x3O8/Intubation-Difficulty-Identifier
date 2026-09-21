"""Re-run the three previously exported sources in an isolated validation DB.

Run from the project root using the project Python environment.
No existing case, review, or original source is modified.
"""
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from airway.analysis import analyze_clip
from airway.db import initialize,transaction
from airway.ingest import now
from airway.research import query,frame_gate,load_frames,setup,case_report,exports

hashes=['66da3d925db1e2e1ab77ccc2ee3d667af3167e80abcb610a52e9359fae658b5b',
        'd126a497be66be16150ae6aa90b3355322efedc0cdf294306118c69bfa5857ff',
        '2753e037bdcc095cdf339e856796b1c13199ecd91ea448f0b336439d370e42cb']
root=Path('data/validation')/str(uuid.uuid4());root.mkdir(parents=True)
db=root/'validation.sqlite3';initialize(db);setup(db)
cid='validation';results=[]
with transaction(db) as c:c.execute('INSERT INTO cases(id,label,created_at) VALUES(?,?,?)',(cid,'Isolated regression validation',now()))
for i,h in enumerate(hashes):
    video=query('data/airway.sqlite3','SELECT * FROM videos WHERE sha256=?',(h,))[0]
    with transaction(db) as c:
        keys=list(video);c.execute('INSERT INTO videos('+','.join(keys)+') VALUES('+','.join('?' for k in keys)+')',[video[k] for k in keys])
        c.execute('INSERT INTO segments(id,case_id,video_id) VALUES(?,?,?)',(str(i),cid,video['id']))
    run=analyze_clip(cid,video['id'],db_path=db)
    frames=load_frames(db,run['run_id'])
    results.append({'source_hash':h,'run_id':run['run_id'],'sampled_frames':len(frames),
                    'tracking_coverage':run['summary']['tracking_coverage'],
                    'mouth_eligible_frames':sum(not frame_gate(f,True) for f in frames),
                    'motion_eligible_frames':sum(not frame_gate(f,False) for f in frames)})
    print(json.dumps(results[-1]),flush=True)
report=case_report(db,cid);digest,files=exports(report)
for kind,content in files.items():(root/f'research-{digest}.{kind}').write_text(content,encoding='utf-8')
(root/'validation.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
print('VALIDATION_DIRECTORY',root.resolve(),flush=True)
