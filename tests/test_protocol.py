import io
import json
import math

import cv2
import numpy as np
import pytest
from PIL import Image

from airway.db import initialize, transaction
from airway.protocol import VIDEO_ROLES, create_video_case, thyromental_result, save_thyromental
from airway.research import setup, case_clips, case_report, evaluate_clip, exports, label_flexion_extension


def confirmations():
    return dict.fromkeys(('thyroid_notch', 'mentum', 'mouth_closed', 'full_extension', 'true_profile', 'same_plane'), True)


def test_thyromental_geometry_and_missing_prerequisites():
    frame = dict(timestamp_ms=100, source_width=200, source_height=200)
    points = [[10, 10], [70, 90], [100, 10], [100, 60]]
    result = thyromental_result(frame, points, 5, .2, 'Reviewer', confirmations())
    assert result['value'] == 10
    assert result['target_px'] == 100
    assert 'threshold' not in result
    for key in confirmations():
        with pytest.raises(ValueError):
            thyromental_result(frame, points, 5, .2, 'Reviewer', dict(confirmations(), **{key: False}))
    for bad in (0, -1, float('nan'), float('inf')):
        with pytest.raises(ValueError):
            thyromental_result(frame, points, bad, .2, 'Reviewer', confirmations())
    with pytest.raises(ValueError):
        thyromental_result(frame, [None]*4, 5, .2, 'Reviewer', confirmations())


def test_combined_front_review_disallows_profile_fallback_and_labels_directions():
    frames = []
    for index in range(40):
        degrees = 0 if index < 10 else (-20 if index < 20 else (30 if index < 30 else 0))
        angle = math.radians(degrees)
        matrix = [[1,0,0,0],[0,math.cos(angle),-math.sin(angle),0],[0,math.sin(angle),math.cos(angle),0],[0,0,0,1]]
        frames.append(dict(timestamp_ms=index*100, valid=True, face_count=1, quality={}, matrix=matrix,
                           profile_pose={'valid':True, 'head_line_angle_degrees':100}, mouth_width_px=80,
                           visible_lip_aperture_px=32, lip_aperture_over_mouth_width=.4, lip_aperture_over_outer_eye_span=.2))
    result = evaluate_clip(frames, VIDEO_ROLES[0], 0, 3900, 0, 500, True, True)
    assert result['state'] == 'accepted'
    assert len(result['metric_reviews']) == 2
    label_flexion_extension(result, True)
    findings = {f['metric']: f for f in result['findings']}
    assert findings['observed_flexion']['value'] == pytest.approx(20)
    assert findings['observed_extension']['value'] == pytest.approx(30)
    assert findings['pitch']['value'] == pytest.approx(50)
    assert 'Camera-relative' in findings['observed_flexion']['label']
    assert findings['visible_lip_aperture_px']['value'] == 32


def uploads(tmp_path):
    result = []
    for index in range(3):
        path = tmp_path / f'test{index}.avi'
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), 10, (64, 64))
        for frame in range(15):
            writer.write(np.full((64,64,3), 30 + index*50 + frame, np.uint8))
        writer.release()
        stream = io.BytesIO(path.read_bytes())
        stream.name = path.name
        result.append(stream)
    return result


def test_upload_decode_persistence_and_stale_thyromental(tmp_path):
    db = tmp_path / 'data' / 'test.db'
    initialize(db); setup(db)
    clips = uploads(tmp_path)
    with pytest.raises(ValueError):
        create_video_case(db, clips, 'Study patient', 'Reviewer', False)
    with pytest.raises(ValueError):
        create_video_case(db, [clips[0]]*3, 'Study patient', 'Reviewer', True)
    cid = create_video_case(db, clips, 'Study patient', 'Reviewer', True)
    saved = case_clips(db, cid)
    assert len(saved) == 3
    assert all(clip['decode_status'] == 'success' for clip in saved)
    assert case_report(db, cid)['thyromental']['state'] == 'unavailable'
    vid = saved[2]['id']
    image = tmp_path/'frame.jpg'; Image.new('RGB', (200,200)).save(image)
    frame = dict(timestamp_ms=100, source_width=200, source_height=200, source_frame_path=str(image))
    artifact = tmp_path/'frames.json'; artifact.write_text(json.dumps({'frames':[frame]}))
    with transaction(db) as conn:
        conn.execute("INSERT INTO analysis_runs(id,case_id,video_id,config_json,state,started_at) VALUES('r',?,?,'{}','completed','1')", (cid,vid))
        conn.execute("INSERT INTO analysis_artifacts(id,run_id,kind,path,sha256,created_at) VALUES('a','r','per_frame_json',?,'test-hash','1')", (str(artifact),))
    result = thyromental_result(frame, [[10,10],[70,10],[10,50],[60,50]], 5, .2, 'Test reviewer', confirmations())
    save_thyromental(db,cid,vid,'r',result)
    report = case_report(db,cid)
    assert report['thyromental']['value'] == 6
    _, output = exports(report)
    assert 'thyromental_distance' in output['csv'] and '6.00 cm' in output['html']
    with transaction(db) as conn:
        conn.execute("INSERT INTO analysis_runs(id,case_id,video_id,config_json,state,started_at) VALUES('r2',?,?,'{}','failed','2')", (cid,vid))
    assert case_report(db,cid)['thyromental']['state'] == 'unavailable'
    with pytest.raises(ValueError):
        save_thyromental(db,cid,vid,'r',result)
