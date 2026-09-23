"""Traceable, reviewer-marked 2-D research measurements (never inferred anatomy)."""
from __future__ import annotations

import base64
import io
import json
import math
import uuid
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from .db import transaction
from .ingest import now
from .video import sha256_file

VERSION = 'projected-anthropometry-1.0'
METRICS = {
    'thyromental_pixels': ('Thyromental distance', 'Mentum (chin)', 'Superior thyroid notch', 'Profile', 'Mouth closed, head extended'),
    'hyomental_pixels': ('Hyomental distance', 'Mentum (chin)', 'Identified / externally marked hyoid point', 'Profile', 'Record neutral or extended posture in notes'),
    'mandible_length_pixels': ('Mandible length', 'Gonion (mandibular angle)', 'Mentum (chin)', 'Profile', 'Mouth closed; specify left or right side'),
    'bigonial_width_pixels': ('Bigonial width', 'Left gonion', 'Right gonion', 'Frontal', 'Mouth closed, neutral frontal head'),
    'thyroid_floor_pixels': ('Thyroid-to-floor-of-mouth distance', 'Superior thyroid notch', 'Verified floor-of-mouth endpoint / external surrogate', 'Profile', 'State the floor-of-mouth endpoint definition in notes'),
    'sternomental_pixels': ('Sternomental distance', 'Upper border of manubrium', 'Mentum (chin)', 'Profile', 'Mouth closed, head extended'),
    'jaw_protrusion': ('Jaw protrusion', 'Upper incisor tip / fixed upper-face point', 'Lower incisor tip / chin surface point', 'Profile', 'Neutral and actively protruded jaw; matched head pose, same side'),
}
BASES = ('Externally identified anatomical endpoints', 'Approximate visible surface proxies')
LIMITATION = ('Projected 2-D research estimate; perspective and endpoint placement affect the value. '
              'Pixels are source-image pixels, not centimetres. Ratios remove uniform scale only; '
              'they do not recover hidden anatomy or remove foreshortening. No clinical thresholds.')


def setup(db):
    with transaction(db) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS research_pixel_reviews '
                     '(id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE, '
                     'video_id TEXT NOT NULL, run_id TEXT NOT NULL, metric TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL)')


def _pair(points, frame):
    try:
        arr = np.asarray(points, dtype=float)
        width, height = float(frame['source_width']), float(frame['source_height'])
    except (TypeError, ValueError, KeyError) as exc:
        raise ValueError('Mark both endpoints on the source frame.') from exc
    if arr.shape != (2, 2) or not np.isfinite(arr).all():
        raise ValueError('Mark two finite endpoints on the source frame.')
    if not all(math.isfinite(v) and v > 0 for v in (width, height)):
        raise ValueError('Invalid source dimensions.')
    if np.any(arr < 0) or np.any(arr >= [width, height]):
        raise ValueError('Endpoint lies outside the source image.')
    return arr


def _norm(pair):
    return float(np.linalg.norm(pair[1] - pair[0]))


def surface_suggestion(metric, frame, side='Left'):
    """Face-oval hints only: these IDs are not verified bony gonion landmarks."""
    if not frame.get('valid') or frame.get('face_count') != 1 or not frame.get('landmarks'):
        return None
    if metric not in ('bigonial_width_pixels', 'mandible_length_pixels'):
        return None
    ids = (172, 397) if metric == 'bigonial_width_pixels' else (172 if side == 'Left' else 397, 152)
    try:
        return _pair([frame['landmarks'][i][:2] for i in ids], frame).tolist()
    except (ValueError, IndexError, TypeError):
        return None


def measure(request, source_frames):
    """Calculate from source coordinates; persistence always reruns this function."""
    metric = request.get('metric')
    if metric not in METRICS:
        raise ValueError('Unknown research measurement.')
    definition = METRICS[metric]
    reviewer, notes = request.get('reviewer', '').strip(), request.get('notes', '').strip()
    if not reviewer or not notes:
        raise ValueError('Reviewer and endpoint/posture notes are required.')
    if request.get('unavailable_reason', '').strip():
        return dict(metric=metric, label=definition[0], state='unavailable', findings=[],
                    reviewer=reviewer, notes=notes, reason=request['unavailable_reason'].strip(), version=VERSION)
    basis = request.get('basis')
    if basis not in BASES or request.get('verified') is not True:
        raise ValueError('Identify the endpoint basis and confirm the visible points, view and posture.')
    if request.get('view') != definition[3]:
        raise ValueError(f'{definition[0]} requires the {definition[3].lower()} view.')
    error = float(request.get('placement_error_px', 0))
    if not math.isfinite(error) or error <= 0:
        raise ValueError('Supply a positive estimated endpoint-placement error in source pixels.')
    timestamps = request.get('timestamps', [])
    expected = 2 if metric == 'jaw_protrusion' else 1
    if len(timestamps) != expected or any(not math.isfinite(float(t)) for t in timestamps):
        raise ValueError('Choose the required source frames.')
    frames = [next((f for f in source_frames if f['timestamp_ms'] == t), None) for t in timestamps]
    if any(f is None for f in frames):
        raise ValueError('Selected timestamp is absent from the current analysis.')
    targets = request.get('targets', [])
    references = request.get('references', [])
    if len(targets) != expected or len(references) not in (0, expected):
        raise ValueError('Incomplete endpoint pairs.')
    target_pairs = [_pair(p, f) for p, f in zip(targets, frames)]
    reference_pairs = [_pair(p, f) for p, f in zip(references, frames)]
    if reference_pairs and not request.get('reference_label', '').strip():
        raise ValueError('Name the reference endpoints so the ratio is reproducible.')
    if any(_norm(p) < max(10, 2 * error + 1) for p in reference_pairs):
        raise ValueError('Reference is too short for the stated endpoint error; use a longer visible reference.')
    proxy = basis == BASES[1]
    label = definition[0] + (' · surface-proxy approximation' if proxy else ' · projected estimate')
    data = dict(metric=metric, label=label, state='reviewed_approximation' if proxy else 'reviewed_image_estimate',
                version=VERSION, basis=basis, reviewer=reviewer, notes=notes, view=request['view'],
                timestamps=timestamps, source_dimensions=[[f['source_width'], f['source_height']] for f in frames],
                targets=[p.tolist() for p in target_pairs], references=[p.tolist() for p in reference_pairs],
                reference_label=request.get('reference_label', ''), placement_error_px=error,
                uncertainty_kind='Reviewer-specified endpoint error, not an empirical confidence interval',
                limitation=LIMITATION, findings=[])
    if metric == 'jaw_protrusion':
        if len(reference_pairs) != 2 or timestamps[1] <= timestamps[0] or request.get('maneuver_verified') is not True:
            raise ValueError('Jaw protrusion needs a neutral frame followed by an observed protrusion, with stable upper-face reference anchors in both.')
        offsets, lengths = [], []
        for target, ref in zip(target_pairs, reference_pairs):
            length = _norm(ref)
            offsets.append(float(np.dot(target[1] - target[0], (ref[1] - ref[0]) / length) / length))
            lengths.append(length)
        delta = offsets[1] - offsets[0]
        # Conservative bound for target, direction and reference-length errors.
        bounds = []
        for target, ref, length in zip(target_pairs, reference_pairs, lengths):
            target_length = _norm(target)
            bounds.append(2 * error / (length - 2 * error)
                          + 4 * error * target_length / (length * (length - 2 * error))
                          + 2 * error * target_length / (length * (length - 2 * error)))
        bound = sum(bounds)
        ratio_range = [delta - bound, delta + bound]
        px_range = [v * scale for v in ratio_range for scale in (lengths[0] - 2 * error, lengths[0] + 2 * error)]
        data.update(normalized_offsets=offsets, reference_lengths_px=lengths,
                    method='Change in lower-minus-upper endpoint offset projected along posterior-to-anterior upper-face axis, normalized separately in each frame',
                    formula='ratio = dot(B1-A1, unit(R1b-R1a))/L1 - dot(B0-A0, unit(R0b-R0a))/L0; px = ratio * L0',
                    direction='Positive means forward along the selected upper-face reference axis; negative means backward.',
                    findings=[dict(metric=metric + '_ratio', label=label + ' / ' + data['reference_label'], value=delta, unit='ratio', range=ratio_range),
                              dict(metric=metric + '_px', label=label + ' (neutral-frame pixel equivalent)', value=delta * lengths[0], unit='px', range=[min(px_range), max(px_range)])])
    else:
        length = _norm(target_pairs[0])
        if length < 2:
            raise ValueError('Measurement endpoints must be at least two source pixels apart.')
        low, high = max(0, length - 2 * error), length + 2 * error
        data.update(method='Reviewer-marked source-pixel Euclidean separation', formula='distance_px = sqrt((Bx-Ax)^2 + (By-Ay)^2)')
        data['findings'].append(dict(metric=metric, label=label, value=length, unit='px', range=[low, high]))
        if reference_pairs:
            ref_length = _norm(reference_pairs[0])
            data['reference_lengths_px'] = [ref_length]
            data['formula'] += '; ratio = distance_px / reference_px (same frame)'
            data['findings'].append(dict(metric=metric + '_ratio', label=label + ' / ' + data['reference_label'],
                                         value=length / ref_length, unit='ratio', range=[low / (ref_length + 2 * error), high / (ref_length - 2 * error)]))
    return data


def _evidence(frame, target, reference):
    with Image.open(frame['source_frame_path']) as source:
        image = source.convert('RGB')
    if image.size != (frame['source_width'], frame['source_height']):
        raise ValueError('Stored evidence image dimensions differ from source coordinates.')
    draw = ImageDraw.Draw(image)
    for points, color, labels in ((target, '#ffb000', ('A', 'B')), (reference, '#00e0c0', ('R1', 'R2'))):
        if not points:
            continue
        draw.line([tuple(p) for p in points], fill=color, width=3)
        for p, label in zip(points, labels):
            x, y = p
            draw.ellipse((x-4,y-4,x+4,y+4), fill=color)
            draw.text((x+7,y), label, fill=color, stroke_width=1, stroke_fill='black')
    stream = io.BytesIO(); image.save(stream, format='JPEG', quality=90)
    return dict(timestamp_ms=frame['timestamp_ms'], source_frame_sha256=sha256_file(Path(frame['source_frame_path'])),
                data_uri='data:image/jpeg;base64,' + base64.b64encode(stream.getvalue()).decode())


def save_review(db, case_id, video_id, run_id, request):
    from .research import case_clips, latest_run, load_frames
    setup(db)
    clips = {v['id']: v for v in case_clips(db, case_id)}
    run = latest_run(db, case_id, video_id)
    if video_id not in clips or not run or run['id'] != run_id or run['state'] != 'completed':
        raise ValueError('Select a current completed run belonging to this case.')
    clip = clips[video_id]
    if sha256_file(Path(clip['source_path'])) != clip['sha256']:
        raise ValueError('The source video changed; re-import and analyze it before reviewing.')
    frames = load_frames(db, run_id)
    result = measure(request, frames)
    result.update(video_id=video_id, run_id=run_id, source_hash=clip['sha256'], file=clip['relative_path'],
                  model_hash=run.get('model_hash'), analysis_config=json.loads(run['config_json']),
                  request=request, evidence_images=[])
    for i, timestamp in enumerate(result.get('timestamps', [])):
        frame = next(f for f in frames if f['timestamp_ms'] == timestamp)
        result['evidence_images'].append(_evidence(frame, result['targets'][i], result['references'][i] if result['references'] else []))
    with transaction(db) as conn:
        conn.execute('INSERT INTO research_pixel_reviews VALUES(?,?,?,?,?,?,?)',
                     (str(uuid.uuid4()), case_id, video_id, run_id, result['metric'], json.dumps(result, allow_nan=False), now()))
        conn.execute('UPDATE report_snapshots SET invalidated_at=? WHERE case_id=? AND invalidated_at IS NULL', (now(), case_id))
    return result


def latest_reviews(db, case_id):
    from .research import case_clips, latest_run
    setup(db)
    clips = {c['id']: c for c in case_clips(db, case_id)}
    with transaction(db) as conn:
        rows = conn.execute('SELECT * FROM research_pixel_reviews WHERE case_id=? ORDER BY created_at DESC,rowid DESC', (case_id,)).fetchall()
    current_runs = {vid: latest_run(db, case_id, vid) for vid in clips}
    source_matches = {}
    seen, results = set(), []
    for row in rows:
        key = (row['video_id'], row['metric'])
        if key in seen or row['video_id'] not in clips:
            continue
        seen.add(key)
        result = json.loads(row['payload'])
        run = current_runs[row['video_id']]
        if row['video_id'] not in source_matches:
            try:
                source_matches[row['video_id']] = sha256_file(Path(clips[row['video_id']]['source_path'])) == clips[row['video_id']]['sha256']
            except OSError:
                source_matches[row['video_id']] = False
        if not run or run['id'] != row['run_id'] or run['state'] != 'completed' or result['source_hash'] != clips[row['video_id']]['sha256'] or not source_matches[row['video_id']]:
            result = {k: result[k] for k in ('metric', 'label', 'video_id', 'run_id', 'source_hash', 'file', 'reviewer')}
            result.update(state='stale', findings=[], reason='Analysis or source changed / unavailable; review the current source frames again.')
        results.append(result)
    for metric, definition in METRICS.items():
        if not any(r['metric'] == metric for r in results):
            results.append(dict(metric=metric, label=definition[0], state='unavailable', findings=[], reason='No reviewed pixel measurement recorded.'))
    return results
