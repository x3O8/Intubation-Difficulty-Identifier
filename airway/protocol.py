"""Three-video intake and reviewer-verified thyromental evidence."""
from __future__ import annotations

import hashlib
import json
import math
import shutil
import uuid
from pathlib import Path

import numpy as np

from .db import transaction
from .ingest import now
from .video import decode_video

VIDEO_ROLES = (
    'Front · mouth open, looking up and down',
    'Front · looking left and right',
    'Side · looking up and down',
)
TMD_SOURCE = 'https://pmc.ncbi.nlm.nih.gov/articles/PMC6748003/'


def create_video_case(db, uploads, label, reviewer, same_patient):
    """Persist three explicitly assigned uploads; never infer patient identity."""
    if not label.strip() or not reviewer.strip() or not same_patient:
        raise ValueError('Provide a case label, your name, and confirmation that all three videos belong to this patient.')
    if len(uploads) != 3 or any(upload is None for upload in uploads):
        raise ValueError('Supply one video for each of the three recording slots.')
    cid = str(uuid.uuid4())
    root = Path(db).resolve().parent / 'participants' / 'unassigned' / 'cases' / cid / 'originals'
    root.mkdir(parents=True)
    records = []
    try:
        for index, upload in enumerate(uploads):
            suffix = Path(upload.name).suffix.lower()
            if suffix not in ('.mp4', '.mov', '.avi', '.mkv', '.webm'):
                raise ValueError('Unsupported video format.')
            vid = str(uuid.uuid4())
            dest = root / (vid + suffix)
            digest = hashlib.sha256()
            upload.seek(0)
            with dest.open('wb') as target:
                for chunk in iter(lambda: upload.read(1024 * 1024), b''):
                    target.write(chunk)
                    digest.update(chunk)
            metadata = decode_video(dest)
            if metadata['status'] != 'success':
                raise ValueError(f'Video {index + 1} could not be fully decoded. Supply a complete playable recording.')
            records.append((vid, dest, digest.hexdigest(), metadata))
        if len({record[2] for record in records}) != 3:
            raise ValueError('The same video was supplied more than once. Supply three distinct recordings.')
        with transaction(db) as conn:
            conn.execute('INSERT INTO cases(id,label,created_at) VALUES(?,?,?)', (cid, label.strip(), now()))
            for index, (vid, dest, digest, metadata) in enumerate(records):
                conn.execute('INSERT INTO videos(id,source_path,relative_path,sha256,bytes,decode_status,metadata_json,created_at) VALUES(?,?,?,?,?,?,?,?)',
                             (vid, str(dest), f'{index+1} · {Path(uploads[index].name).name}', digest, dest.stat().st_size, 'success', json.dumps(metadata), now()))
                conn.execute('INSERT INTO segments(id,case_id,video_id,reason) VALUES(?,?,?,?)',
                             (str(uuid.uuid4()), cid, vid, json.dumps({'role': VIDEO_ROLES[index], 'same_patient_confirmed_by': reviewer.strip()})))
        return cid
    except Exception:
        # Only this new UUID directory is owned by this operation.
        shutil.rmtree(root.parent)
        raise


def thyromental_result(frame, points, reference_cm, uncertainty_cm, reviewer, confirmations):
    """Calibrated 2D estimate, only with verified anatomy, posture and geometry."""
    required = ('thyroid_notch', 'mentum', 'mouth_closed', 'full_extension', 'true_profile', 'same_plane')
    if not all(confirmations.get(key) is True for key in required):
        raise ValueError('Verify both anatomical endpoints, mouth closed, full extension, true profile and a same-plane scale.')
    if not reviewer.strip():
        raise ValueError('Reviewer name is required.')
    if not all(math.isfinite(v) for v in (reference_cm, uncertainty_cm)) or reference_cm <= 0 or uncertainty_cm < 0:
        raise ValueError('Supply a positive reference size and a finite nonnegative error bound.')
    if len(points) != 4 or any(point is None for point in points):
        raise ValueError('Mark the mentum, thyroid notch and both reference endpoints on this frame.')
    for point in points:
        if len(point) != 2 or not all(math.isfinite(v) for v in point):
            raise ValueError('Invalid endpoint coordinates.')
        if not 0 <= point[0] < frame['source_width'] or not 0 <= point[1] < frame['source_height']:
            raise ValueError('Endpoints must lie inside the source image.')
    target_px = float(np.linalg.norm(np.asarray(points[0]) - points[1]))
    reference_px = float(np.linalg.norm(np.asarray(points[2]) - points[3]))
    if min(target_px, reference_px) < 10:
        raise ValueError('Both measurement lines must span at least 10 source pixels.')
    value = target_px * reference_cm / reference_px
    return {'metric': 'thyromental_distance', 'state': 'reviewed_estimate', 'value': value, 'unit': 'cm',
            'timestamp_ms': frame['timestamp_ms'], 'points': points,
            'reference_cm': reference_cm, 'reference_px': reference_px, 'target_px': target_px,
            'uncertainty_cm': uncertainty_cm, 'reviewer': reviewer.strip(), 'confirmations': confirmations,
            'method': 'Reviewer-marked mentum to thyroid notch, same-frame calibrated image estimate',
            'source': TMD_SOURCE,
            'limitation': 'Reviewer-specified error bound; unvalidated 2D estimate, subject to perspective and landmark error. No airway prediction.'}


def save_thyromental(db, case_id, video_id, run_id, result):
    from .research import case_clips, latest_run, load_frames
    if video_id not in {clip['id'] for clip in case_clips(db, case_id)}:
        raise ValueError('Video does not belong to this case.')
    run = latest_run(db, case_id, video_id)
    if not run or run['id'] != run_id or run['state'] != 'completed':
        raise ValueError('Review the current completed analysis first.')
    frame = next((f for f in load_frames(db, run_id) if f['timestamp_ms'] == result['timestamp_ms']), None)
    if frame is None:
        raise ValueError('The selected source frame is unavailable.')
    checked = thyromental_result(frame, result['points'], result['reference_cm'], result['uncertainty_cm'], result['reviewer'], result['confirmations'])
    import base64
    checked['evidence_image'] = 'data:image/jpeg;base64,' + base64.b64encode(Path(frame['source_frame_path']).read_bytes()).decode('ascii')
    checked.update(video_id=video_id, run_id=run_id)
    with transaction(db) as conn:
        conn.execute('INSERT INTO research_thyromental VALUES(?,?,?,?,?)',
                     (str(uuid.uuid4()), case_id, video_id, json.dumps(checked, allow_nan=False), now()))
        conn.execute('UPDATE report_snapshots SET invalidated_at=? WHERE case_id=? AND invalidated_at IS NULL', (now(), case_id))


def latest_thyromental(db, case_id):
    from .research import query, latest_run, case_clips
    rows = query(db, 'SELECT payload FROM research_thyromental WHERE case_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1', (case_id,))
    missing = {'state': 'unavailable', 'reason': 'Verify mentum and thyroid notch on a mouth-closed extended profile frame with a same-plane known-size reference.'}
    if not rows:
        return missing
    result = json.loads(rows[0]['payload'])
    clips = {clip['id']: clip for clip in case_clips(db, case_id)}
    run = latest_run(db, case_id, result['video_id'])
    if result['video_id'] not in clips or not run or run['id'] != result['run_id'] or run['state'] != 'completed':
        return dict(missing, reason='Previous thyromental evidence is stale. Review the current analysis.')
    result['source_hash'] = clips[result['video_id']]['sha256']
    return result
