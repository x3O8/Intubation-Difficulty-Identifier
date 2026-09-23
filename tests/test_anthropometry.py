"""Geometry invariants, missing anatomy, persistence and report provenance."""
import copy
import csv
import io
import json
import math
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from airway.anthropometry import METRICS, BASES, measure, save_review, latest_reviews
from airway.db import initialize, transaction
from airway.landmarks import profile_pose
from airway.research import setup, case_report, exports
from airway.video import sha256_file


def frame(t=0):
    return dict(timestamp_ms=t, source_width=1000, source_height=1600)


def request(metric='thyromental_pixels'):
    return dict(metric=metric, reviewer='Researcher', notes='Visible surface points, full extension, right side',
                basis=BASES[1], verified=True, view=METRICS[metric][3], placement_error_px=1,
                timestamps=[0], targets=[[[100,100],[160,180]]], references=[[[200,100],[200,150]]],
                reference_label='Explicit reference pair')


@pytest.mark.parametrize('metric', [m for m in METRICS if m != 'jaw_protrusion'])
def test_distances_ratios_and_scale_invariance(metric):
    req = request(metric)
    output = measure(req, [frame()])
    assert [f['value'] for f in output['findings']] == [100, 2]
    assert output['findings'][0]['range'] == [98, 102]
    assert output['findings'][1]['range'] == pytest.approx([98/52, 102/48])
    req['targets'] = (np.asarray(req['targets']) * 2).tolist()
    req['references'] = (np.asarray(req['references']) * 2).tolist()
    scaled = measure(req, [frame()])
    assert [f['value'] for f in scaled['findings']] == [200, 2]
    req['references'] = []
    assert len(measure(req, [frame()])['findings']) == 1


def test_jaw_change_invariant_to_translation_rotation_and_uniform_scale():
    req = request('jaw_protrusion')
    req.update(timestamps=[0,1000], targets=[[[300,300],[310,320]],[[300,300],[330,320]]],
               references=[[[200,200],[300,200]],[[200,200],[300,200]]], maneuver_verified=True)
    out = measure(req, [frame(),frame(1000)])
    assert out['findings'][0]['value'] == pytest.approx(.2)
    assert out['findings'][1]['value'] == pytest.approx(20)
    angle=math.radians(30); rotation=np.array([[math.cos(angle),-math.sin(angle)],[math.sin(angle),math.cos(angle)]])
    for field in ('targets','references'):
        req[field][1] = (2 * np.asarray(req[field][1]) @ rotation.T + [200,200]).tolist()
    transformed = measure(req, [frame(),frame(1000)])
    assert transformed['findings'][0]['value'] == pytest.approx(.2)
    assert transformed['findings'][1]['value'] == pytest.approx(20)
    req['maneuver_verified'] = False
    with pytest.raises(ValueError): measure(req, [frame(),frame(1000)])


def test_missing_points_invalid_references_and_unavailable():
    for change in ({'verified':False}, {'targets':[[None,None]]}, {'placement_error_px':float('nan')},
                   {'references':[[[1,1],[2,1]]]}, {'timestamps':[90]}, {'view':'Frontal'},
                   {'targets':[[[0,0],[1000,10]]]}, {'reference_label':''}):
        req=request();req.update(change)
        with pytest.raises(ValueError): measure(req,[frame()])
    req=request('hyomental_pixels');req.update(unavailable_reason='Hyoid cannot be located', targets=[], timestamps=[], references=[], verified=False)
    assert measure(req,[frame()])['findings'] == []


def test_profile_angle_uses_pixel_aspect_ratio():
    points = [SimpleNamespace(x=.5,y=.5,visibility=1) for _ in range(33)]
    points[0] = SimpleNamespace(x=.75,y=.25,visibility=1)
    # Delta in a 400x800 image is +100,-200 pixels (not +.25,-.25).
    result = profile_pose(SimpleNamespace(pose_landmarks=[points]),400,800)
    assert result['head_line_angle_degrees'] == pytest.approx(math.degrees(math.atan2(-200,100)))
    assert result['angle_coordinate_space'] == 'source_pixels_v1'
    assert not profile_pose(SimpleNamespace(pose_landmarks=[points]),0,800)['valid']


@pytest.fixture
def stored_case(tmp_path):
    db=tmp_path/'research.db';initialize(db);setup(db)
    source=tmp_path/'source.mp4';source.write_bytes(b'synthetic source identity')
    image=tmp_path/'source.jpg';Image.new('RGB',(1000,1600),'white').save(image)
    f=dict(frame(),source_frame_path=str(image))
    artifact=tmp_path/'frames.json';artifact.write_text(json.dumps({'frames':[f]}))
    digest=sha256_file(source)
    with transaction(db) as conn:
        for cid in ('A','B'): conn.execute('INSERT INTO cases(id,label,created_at) VALUES(?,?,?)',(cid,cid,'1'))
        conn.execute("INSERT INTO videos(id,source_path,relative_path,sha256,bytes,created_at) VALUES('v',?,'source.mp4',?,1,'1')",(str(source),digest))
        conn.execute("INSERT INTO segments(id,case_id,video_id) VALUES('s','A','v')")
        conn.execute("INSERT INTO analysis_runs(id,case_id,video_id,config_json,state,started_at) VALUES('r','A','v','{}','completed','1')")
        conn.execute("INSERT INTO analysis_artifacts(id,run_id,kind,path,sha256,created_at) VALUES('a','r','per_frame_json',?,'hash','1')",(str(artifact),))
    return db,source


def test_persistence_exports_case_isolation_and_stale_run(stored_case):
    db,source=stored_case
    req=request();req['notes']='<script>bad</script>'
    saved=save_review(db,'A','v','r',req)
    assert saved['source_hash'] == sha256_file(source)
    assert saved['evidence_images'][0]['data_uri'].startswith('data:image/jpeg;base64,')
    assert all(not r['findings'] for r in latest_reviews(db,'B'))
    with pytest.raises(ValueError): save_review(db,'B','v','r',req)
    report=case_report(db,'A');_,files=exports(report)
    assert '<script>bad</script>' not in files['html']
    assert '&lt;script&gt;bad&lt;/script&gt;' in files['html']
    rows=list(csv.DictReader(io.StringIO(files['csv'])))
    assert any(r['metric']=='thyromental_pixels_ratio' and float(r['value'])==2 for r in rows)
    assert 'targets' in rows[0]
    with transaction(db) as conn:
        conn.execute("INSERT INTO analysis_runs(id,case_id,video_id,config_json,state,started_at) VALUES('r2','A','v','{}','failed','2')")
    stale=next(r for r in latest_reviews(db,'A') if r['metric']=='thyromental_pixels')
    assert stale['state']=='stale' and stale['findings']==[]
    assert 'targets' not in stale
    with pytest.raises(ValueError): save_review(db,'A','v','r',req)


def test_changed_source_blocks_new_measurement(stored_case):
    db,source=stored_case
    save_review(db,'A','v','r',request())
    source.write_bytes(b'changed')
    assert latest_reviews(db,'A')[0]['state']=='stale'
    with pytest.raises(ValueError,match='source video changed'):
        save_review(db,'A','v','r',request())


def test_signed_csv_values_remain_numeric_and_legacy_profile_flagged(stored_case):
    from airway.research import save_review as save_motion
    db,_=stored_case
    finding=dict(metric='pitch',label='Profile shoulder-to-nose angle',value=-20.,unit='degree',timestamp_ms=0.)
    save_motion(db,'A','v','r','Reviewer',dict(role='Head flexion / extension',state='accepted',reasons=[],findings=[finding]))
    report=case_report(db,'A')
    assert report['clips'][0]['state']=='needs review'
    assert 'aspect ratio' in report['clips'][0]['reasons'][0]
    _,files=exports(report)
    row=next(r for r in csv.DictReader(io.StringIO(files['csv'])) if r['metric']=='pitch')
    assert float(row['value'])==-20


def test_review_ui_saves_pixel_value_and_renders_report(stored_case):
    from streamlit.testing.v1 import AppTest
    db,_=stored_case
    app=AppTest.from_string(f'from airway.ui.research_workspace import workspace\nworkspace({str(db)!r})',default_timeout=30).run()
    assert not app.exception
    assert len(next(s for s in app.selectbox if s.label=='Research measurement').options)==7
    next(s for s in app.selectbox if s.label=='Observed view').set_value('Profile')
    app.session_state['anthro_targetArthyromental_pixels00_points']={'Point A':[100.,100.],'Point B':[160.,180.]}
    app.session_state['anthro_refArthyromental_pixels00_points']={'Point A':[200.,100.],'Point B':[200.,150.]}
    app.run()
    next(s for s in app.text_area if s.label.startswith('Endpoint identity')).set_value('Visible surface estimate, mouth closed extension')
    next(s for s in app.text_input if s.label=='Measurement reviewer').set_value('Tester')
    next(s for s in app.checkbox if s.label.startswith('I checked the points')).check()
    next(b for b in app.button if b.label=='Save pixel / ratio review').click().run()
    assert not app.exception
    result=next(r for r in latest_reviews(db,'A') if r['metric']=='thyromental_pixels')
    assert result['findings'][0]['value']==100
    app.run();assert not app.exception
    next(s for s in app.selectbox if s.label=='Research measurement').set_value('jaw_protrusion').run()
    assert not app.exception
    assert any(s.label=='Protruded jaw frame' for s in app.select_slider)
