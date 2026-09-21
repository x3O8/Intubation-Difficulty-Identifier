import json
import math

import numpy as np
import pytest

from airway.db import initialize, transaction
from airway.research import (ROLES, case_report, distance_result, evaluate_clip,
    exports, save_distance, save_review, setup, manual_motion)


def frames():
    return [dict(timestamp_ms=i*100,valid=True,face_count=1,quality={},matrix=np.eye(4).tolist(),
                 mouth_width_px=80.,visible_lip_aperture_px=32.,lip_aperture_over_mouth_width=.4,
                 lip_aperture_over_outer_eye_span=.2) for i in range(30)]


def evaluate(f,role=ROLES[1]):
    return evaluate_clip(f,role,0,2900,0,500,True,True)


def test_sparse_tracking_fails_even_when_reviewer_confirms():
    f=frames()
    for frame in f[3:]:frame['valid']=False
    result=evaluate(f)
    assert result['state']=='insufficient'
    assert result['findings'][0]['label'].startswith('Candidate ')


def test_low_coverage_motion_still_surfaces_reviewable_peak_candidates():
    f=frames()
    for index, frame in enumerate(f):
        theta=math.radians(-20 + index * 2)
        frame['matrix']=[[math.cos(theta),0,math.sin(theta),0],[0,1,0,0],[-math.sin(theta),0,math.cos(theta),0],[0,0,0,1]]
        if index not in (0, 10, 20, 29): frame['valid']=False
    result=evaluate(f,ROLES[2])
    assert result['state']=='insufficient'
    assert len(result['peak_evidence'])==2
    assert result['findings'][0]['label'].startswith('Candidate ')


def test_peak_window_coverage_can_accept_endpoints_despite_sparse_transitions():
    f=frames()
    for index, frame in enumerate(f):
        theta=math.radians(-20 + index * 2)
        frame['matrix']=[[math.cos(theta),0,math.sin(theta),0],[0,1,0,0],[-math.sin(theta),0,math.cos(theta),0],[0,0,0,1]]
        if 8 <= index <= 21: frame['valid']=False
    result=evaluate(f,ROLES[2])
    assert result['state']=='accepted'
    assert result['coverage'] < .70
    assert result['endpoint_window_coverage']['passes']


def test_single_spike_does_not_supply_representative_frame():
    f=frames();f[15]['lip_aperture_over_mouth_width']=3.0
    result=evaluate(f)
    assert result['state']=='accepted'
    assert next(x['value'] for x in result['findings'] if x['unit']=='ratio')==.4
    assert len({x['timestamp_ms'] for x in result['findings']})==1


def test_low_coverage_mouth_still_returns_a_peak_candidate_for_review():
    f=frames()
    for index, frame in enumerate(f):
        if index not in range(10, 18): frame['valid']=False
    result=evaluate(f)
    assert result['state']=='insufficient'
    assert result['findings'][0]['label'].startswith('Candidate ')


def test_profile_pose_fallback_selects_flexion_endpoints_without_face_mesh():
    f=frames()
    for index, frame in enumerate(f):
        frame.update(valid=False,face_count=0,matrix=None,
                     profile_pose={'valid':True,'head_line_angle_degrees':-30 + index * 2})
    result=evaluate(f,ROLES[3])
    assert result['state']=='accepted'
    assert len(result['peak_evidence'])==2
    assert 'shoulder-to-nose' in result['findings'][0]['label']


def test_profile_mouth_blocked_but_motion_can_pass():
    f=frames();theta=math.radians(65)
    for row in f:
        row['matrix']=[[math.cos(theta),0,math.sin(theta),0],[0,1,0,0],[-math.sin(theta),0,math.cos(theta),0],[0,0,0,1]]
    assert evaluate(f)['state']=='insufficient'
    result=evaluate(f,ROLES[2])
    assert result['state']=='insufficient'
    assert 'Unable to identify two distinct maneuver endpoint frames' in result['reasons']


def test_profile_flexion_reports_model_limitation_and_manual_review_keeps_role():
    f=frames()
    for frame in f: frame.update(valid=False,face_count=0)
    result=evaluate(f,ROLES[3])
    assert any('No face or profile-pose tracking is available' in reason for reason in result['reasons'])
    source={'timestamp_ms':0,'source_width':100,'source_height':100}
    moved=dict(source,timestamp_ms=1000)
    manual=manual_motion(source,moved,[[10,10],[40,10],[10,10],[10,40]],True,True,ROLES[3])
    assert manual['role']==ROLES[3] and manual['state']=='accepted'


def test_motion_uses_the_role_specific_peak_frames_not_percentiles():
    f=frames()
    for index, frame in enumerate(f):
        theta=math.radians(-30 + index * 2)
        frame['matrix']=[[math.cos(theta),0,math.sin(theta),0],[0,1,0,0],[-math.sin(theta),0,math.cos(theta),0],[0,0,0,1]]
    result=evaluate(f,ROLES[2])
    assert result['state']=='accepted'
    assert len(result['peak_evidence'])==2
    assert result['peak_evidence'][0]['timestamp_ms']==0
    assert result['peak_evidence'][1]['timestamp_ms']==2900
    assert 'peak-to-peak' in result['findings'][0]['label']


def test_threshold_uncertainty_and_strict_boundary():
    args=('Manual interincisor measurement','Reviewer','Ruler at maximum opening')
    assert distance_result(2.5,.2,*args)['status']=='Below reference threshold'
    assert distance_result(2.9,.2,*args)['status'].startswith('Threshold overlap')
    assert distance_result(3,0,*args)['status']=='Threshold not met'

def test_distance_factor_assessment_is_not_an_intubation_verdict():
    args=('Manual interincisor measurement','reviewer','timestamped direct measurement')
    flagged=distance_result(2.5,.2,*args)
    clear=distance_result(3.2,.1,*args)
    assert 'factor present' in flagged['factor_assessment']
    assert 'alone' in clear['factor_assessment']
    assert 'intubation' not in flagged['factor_assessment'].lower()
    with pytest.raises(ValueError):distance_result(float('nan'),0,*args)


def test_manual_lateral_measurement_checks_geometry():
    a={'timestamp_ms':0,'source_width':100,'source_height':100}
    b=dict(a,timestamp_ms=1000)
    points=[[10,10],[40,10],[10,10],[10,40]]
    assert manual_motion(a,b,points,True,True)['findings'][0]['value']==90
    with pytest.raises(ValueError):manual_motion(a,a,points,True,True)
    with pytest.raises(ValueError):manual_motion(a,b,points,False,True)
    with pytest.raises(ValueError):manual_motion(a,b,[[0,0],[200,0],[1,1],[20,20]],True,True)


def test_latest_run_invalidates_review_and_missing_clips_count(tmp_path):
    db=tmp_path/'research.db';initialize(db);setup(db)
    with transaction(db) as c:
        c.execute("INSERT INTO cases(id,label,created_at) VALUES('case','Test','1')")
        for i in range(3):
            c.execute('INSERT INTO videos(id,source_path,relative_path,sha256,bytes,created_at) VALUES(?,?,?,?,1,?)',(str(i),str(i),str(i),'hash','1'))
            c.execute('INSERT INTO segments(id,case_id,video_id) VALUES(?,?,?)',(str(i),'case',str(i)))
        c.execute("INSERT INTO analysis_runs(id,case_id,video_id,config_json,state,started_at) VALUES('r','case','0','{}','completed','1')")
    save_review(db,'case','0','r','reviewer',evaluate(frames()))
    report=case_report(db,'case')
    assert report['clips_accepted']==1 and report['clips_expected']==3
    before,_=exports(report)
    d=distance_result(2.5,.2,'Manual interincisor measurement','Tester','Measured <test>')
    save_distance(db,'case',d)
    after,files=exports(case_report(db,'case'))
    assert before!=after and 'interincisor_distance' in files['csv']
    assert '&lt;test&gt;' in files['html']
    assert json.loads(files['json'])['distance_assessment']['value']==2.5
    with transaction(db) as c:
        c.execute("INSERT INTO analysis_runs(id,case_id,video_id,config_json,state,started_at) VALUES('r2','case','0','{}','failed','2')")
    assert case_report(db,'case')['clips_accepted']==0
    with pytest.raises(ValueError):save_review(db,'case','0','r','reviewer',evaluate(frames()))
