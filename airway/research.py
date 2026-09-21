"""Versioned research review, quality gates, and reproducible case reports."""
from __future__ import annotations

import csv
import base64
import hashlib
import html
import io
import json
import math
import uuid
from pathlib import Path

import numpy as np

from .db import transaction
from .ingest import now
from .measurements import euler_zyx_degrees, relative_rotation
from .measurements import line_angle_degrees, relative_angle

VERSION = 'research-review-2.0'
POLICY = {'minimum_frames': 10, 'minimum_duration_ms': 1000,
          'minimum_coverage': 0.70, 'maximum_frontal_yaw_deg': 25,
          'minimum_mouth_width_px': 20, 'minimum_eye_span_px': 40}
SOURCE = 'https://www.asahq.org/~/media/sites/asahq/files/public/resources/standards-guidelines/practice-guidelines-for-management-of-the-difficult-airway.pdf'
ROLES = ['Unassigned', 'Frontal mouth opening', 'Head rotation', 'Head flexion / extension', 'Lateral movement']
MOTION_AXES = {
    'Head rotation': ('yaw', 'left/right rotation'),
    'Head flexion / extension': ('pitch', 'flexion/extension'),
    'Lateral movement': ('roll', 'lateral bend'),
}


def setup(db):
    with transaction(db) as c:
        c.execute('CREATE TABLE IF NOT EXISTS research_reviews (id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE, video_id TEXT NOT NULL, run_id TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL)')
        c.execute('CREATE TABLE IF NOT EXISTS research_distances (id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE, payload TEXT NOT NULL, created_at TEXT NOT NULL)')


def query(db, sql, args=()):
    with transaction(db) as c:
        return [dict(r) for r in c.execute(sql, args)]


def case_clips(db, case_id):
    case = query(db, 'SELECT * FROM cases WHERE id=? AND deleted_at IS NULL', (case_id,))
    if not case:
        raise ValueError('Case not found')
    pid = case[0]['participant_id']
    if pid:
        return query(db, "SELECT DISTINCT v.* FROM videos v JOIN assignments a ON a.video_id=v.id WHERE a.participant_id=? AND a.status='confirmed' AND a.active=1 ORDER BY v.relative_path", (pid,))
    return query(db, 'SELECT DISTINCT v.* FROM videos v JOIN segments s ON s.video_id=v.id WHERE s.case_id=? ORDER BY v.relative_path', (case_id,))


def latest_run(db, case_id, video_id):
    runs = query(db, 'SELECT * FROM analysis_runs WHERE case_id=? AND video_id=? ORDER BY started_at DESC,rowid DESC LIMIT 1', (case_id, video_id))
    return runs[0] if runs else None


def load_frames(db, run_id):
    rows = query(db, "SELECT path FROM analysis_artifacts WHERE run_id=? AND kind='per_frame_json'", (run_id,))
    if not rows:
        raise ValueError('No frame artifact; analyze this clip first.')
    return json.loads(Path(rows[0]['path']).read_text(encoding='utf-8'))['frames']


def frame_gate(frame, mouth=False):
    reasons = []
    if not frame.get('valid') or frame.get('face_count') != 1:
        return ['Face tracking unavailable or ambiguous']
    quality = frame.get('quality', {})
    if quality.get('laplacian_variance', 100) < 15:
        reasons.append('Blurred frame')
    if quality.get('dark_fraction', 0) > .60 or quality.get('clipped_fraction', 0) > .60:
        reasons.append('Extreme exposure')
    if mouth:
        width = frame.get('mouth_width_px')
        ratio = frame.get('lip_aperture_over_outer_eye_span')
        aperture = frame.get('visible_lip_aperture_px')
        if any(frame.get(k) is None or not math.isfinite(frame[k]) or frame[k] < 0 for k in ('visible_lip_aperture_px','lip_aperture_over_mouth_width','lip_aperture_over_outer_eye_span')):
            reasons.append('Invalid mouth measurement')
        if width is None or not math.isfinite(width) or width < POLICY['minimum_mouth_width_px']:
            reasons.append('Mouth too small or foreshortened')
        if ratio is None or aperture is None or not math.isfinite(ratio) or ratio < 0:
            reasons.append('Eye reference unavailable')
        elif ratio > 0 and aperture / ratio < POLICY['minimum_eye_span_px']:
            reasons.append('Eye reference too small or foreshortened')
    matrix = frame.get('matrix')
    if matrix is None:
        reasons.append('Pose unavailable')
    else:
        try:
            angles = euler_zyx_degrees(np.asarray(matrix)[:3, :3])
            if mouth and abs(angles['yaw']) > POLICY['maximum_frontal_yaw_deg']:
                reasons.append('Mouth view is not sufficiently frontal')
        except (ValueError, IndexError):
            reasons.append('Invalid pose')
    return reasons


def role_frame_gate(frame, role):
    pose = frame.get('profile_pose') or {}
    if role == 'Head flexion / extension' and pose.get('valid'):
        quality = frame.get('quality', {})
        reasons = []
        if quality.get('laplacian_variance', 100) < 15: reasons.append('Blurred frame')
        if quality.get('dark_fraction', 0) > .60 or quality.get('clipped_fraction', 0) > .60: reasons.append('Extreme exposure')
        return reasons
    return frame_gate(frame, role == ROLES[1])


def select_motion_peak_frames(poses, role):
    """Choose the two maneuver endpoints, never generic percentile frames."""
    if role not in MOTION_AXES or len(poses) < 2:
        return None
    axis, maneuver = MOTION_AXES[role]
    ordered = sorted(poses, key=lambda item: item['timestamp_ms'])
    values = np.asarray([item[axis] for item in ordered], dtype=float)
    # A short median window rejects isolated tracker spikes while retaining the
    # actual endpoint of a deliberate slow head movement.
    smooth = np.asarray([
        np.median(values[max(0, index - 2):min(len(values), index + 3)])
        for index in range(len(values))
    ])
    low_index, high_index = int(np.argmin(smooth)), int(np.argmax(smooth))
    if low_index == high_index:
        return None
    low, high = ordered[low_index], ordered[high_index]
    return {
        'axis': axis,
        'maneuver': maneuver,
        'excursion_degrees': float(abs(smooth[high_index] - smooth[low_index])),
        'endpoints': [
            {'label': f'Peak negative {axis} ({maneuver})', 'timestamp_ms': low['timestamp_ms'], 'value_degrees': float(smooth[low_index])},
            {'label': f'Peak positive {axis} ({maneuver})', 'timestamp_ms': high['timestamp_ms'], 'value_degrees': float(smooth[high_index])},
        ],
    }


def select_mouth_peak_frame(frames):
    """Select maximum sustained aperture, rejecting a one-frame landmark spike."""
    if not frames: return None
    values = np.asarray([frame['lip_aperture_over_mouth_width'] for frame in frames], dtype=float)
    smooth = np.asarray([np.median(values[max(0, i - 2):min(len(values), i + 3)]) for i in range(len(values))])
    return frames[int(np.argmax(smooth))]


def endpoint_window_coverage(selected, usable, timestamps, radius_ms=250):
    windows=[]
    for timestamp in timestamps:
        total=sum(abs(frame['timestamp_ms']-timestamp)<=radius_ms for frame in selected)
        valid=sum(abs(frame['timestamp_ms']-timestamp)<=radius_ms for frame in usable)
        windows.append({'timestamp_ms':timestamp,'sampled_frames':total,'usable_frames':valid,
                        'coverage':valid/total if total else 0.0})
    return {'radius_ms':radius_ms,'windows':windows,
            'passes':bool(windows) and all(window['sampled_frames']>=3 and window['coverage']>=.60 for window in windows)}


def evaluate_clip(frames, role, start, end, neutral_start, neutral_end, fixed_camera, visible):
    bounds = [start, end, neutral_start, neutral_end]
    if not all(math.isfinite(v) for v in bounds) or start >= end or neutral_start > neutral_end:
        raise ValueError('Choose finite, ordered intervals of nonzero maneuver duration.')
    if not frames or start < frames[0]['timestamp_ms'] or end > frames[-1]['timestamp_ms']:
        raise ValueError('Review interval falls outside this clip.')
    selected = [f for f in frames if start <= f['timestamp_ms'] <= end]
    mouth = role == ROLES[1]
    usable = [f for f in selected if not role_frame_gate(f, role)]
    coverage = len(usable) / len(selected) if selected else 0
    reasons = []
    if role not in ROLES[1:]: reasons.append('Assign a view / maneuver')
    if not visible: reasons.append('Confirm landmark visibility and performed maneuver')
    if len(usable) < POLICY['minimum_frames']: reasons.append('Fewer than 10 usable frames')
    if end - start < POLICY['minimum_duration_ms']: reasons.append('Review at least one second')
    global_coverage_low = coverage < POLICY['minimum_coverage']
    unavailable_faces = sum(not f.get('valid') or f.get('face_count') != 1 for f in selected)
    if (role == 'Head flexion / extension' and selected and
            unavailable_faces / len(selected) >= 0.70 and
            not any((f.get('profile_pose') or {}).get('valid') for f in selected)):
        reasons.append('No face or profile-pose tracking is available for most frames in this flexion/extension view.')
    findings = []
    evidence = None
    peak_evidence = []
    endpoint_coverage = None
    if mouth and usable:
        # One sustained maximum-opening frame: all ratios and pixel distances
        # share its timestamp. Do not divide separately maximized distances.
        best = select_mouth_peak_frame(usable)
        evidence = best['timestamp_ms']
        endpoint_coverage = endpoint_window_coverage(selected, usable, [evidence])
        if not endpoint_coverage['passes']:
            reasons.append('Peak-frame coverage is too sparse for mouth-opening evidence')
        prefix = 'Candidate ' if reasons else ''
        for key, label, unit in [('visible_lip_aperture_px','Visible lip aperture','px'), ('mouth_width_px','Mouth width','px'), ('lip_aperture_over_mouth_width','Aperture / mouth width','ratio'), ('lip_aperture_over_outer_eye_span','Aperture / eye span','ratio')]:
            findings.append({'metric': key, 'label': prefix + label, 'value': best[key], 'unit': unit, 'timestamp_ms': evidence})
    elif role in MOTION_AXES:
        neutral = [f for f in frames if neutral_start <= f['timestamp_ms'] <= neutral_end and not role_frame_gate(f, role)]
        if not fixed_camera: reasons.append('Confirm fixed camera for motion measurements')
        if not neutral: reasons.append('Neutral interval has no usable pose')
        if fixed_camera and neutral and len(usable) >= 2:
            profile_usable = [f for f in usable if (f.get('profile_pose') or {}).get('valid')]
            profile_neutral = [f for f in neutral if (f.get('profile_pose') or {}).get('valid')]
            if role == 'Head flexion / extension' and len(profile_usable) >= 2 and profile_neutral:
                reference = float(np.mean([f['profile_pose']['head_line_angle_degrees'] for f in profile_neutral]))
                poses = [{'pitch': f['profile_pose']['head_line_angle_degrees'] - reference, 'method': 'profile_pose'} for f in profile_usable]
                pose_frames = profile_usable
            else:
                face_usable = [f for f in usable if f.get('matrix')]
                face_neutral = [f for f in neutral if f.get('matrix')]
                if not face_usable or not face_neutral:
                    reasons.append('No eligible pose signal for maneuver endpoint selection')
                    poses=[]; pose_frames=[]
                else:
                    reference = np.mean([np.asarray(f['matrix'])[:3,:3] for f in face_neutral],axis=0)
                    poses = [euler_zyx_degrees(relative_rotation(reference,np.asarray(f['matrix'])[:3,:3])) for f in face_usable]
                    pose_frames = face_usable
            for pose, frame in zip(poses, pose_frames): pose['timestamp_ms'] = frame['timestamp_ms']
            peaks = select_motion_peak_frames(poses, role)
            if not peaks:
                reasons.append('Unable to identify two distinct maneuver endpoint frames')
            else:
                peak_evidence = peaks['endpoints']
                endpoint_coverage = endpoint_window_coverage(selected, usable, [point['timestamp_ms'] for point in peak_evidence])
                if not endpoint_coverage['passes']:
                    reasons.append('Peak-frame coverage is too sparse for motion endpoint evidence')
                prefix = 'Candidate ' if reasons else ''
                label = f"{prefix}camera-relative {peaks['maneuver']} peak-to-peak excursion"
                if poses and poses[0].get('method') == 'profile_pose':
                    label = f"{prefix}profile shoulder-to-nose {peaks['maneuver']} peak-to-peak change"
                findings.append({'metric': peaks['axis'],
                                 'label': label,
                                 'value': peaks['excursion_degrees'], 'unit':'degree',
                                 'timestamp_ms': [point['timestamp_ms'] for point in peak_evidence]})
        elif len(usable) < 2:
            reasons.append('Fewer than two usable frames for endpoint selection')
    if global_coverage_low and endpoint_coverage is None:
        reasons.append('Usable coverage below 70% in selected interval')
    return {'version':VERSION,'policy':POLICY,'role':role,'interval_ms':[start,end],
            'neutral_interval_ms':[neutral_start,neutral_end],'camera_fixed':fixed_camera,
            'visibility_confirmed':visible,'sampled_frames':len(selected),'usable_frames':len(usable),
            'coverage':coverage,'state':'accepted' if not reasons else 'insufficient',
            'reasons':reasons,'findings':findings,'evidence_timestamp_ms':evidence,
            'peak_evidence':peak_evidence,'endpoint_window_coverage':endpoint_coverage}


def save_review(db, case_id, video_id, run_id, reviewer, result):
    if not reviewer.strip(): raise ValueError('Reviewer name is required')
    if video_id not in {c['id'] for c in case_clips(db,case_id)}:
        raise ValueError('Video does not belong to this case')
    run = latest_run(db, case_id, video_id)
    if not run or run['id'] != run_id or run['state'] != 'completed':
        raise ValueError('This run is no longer current. Review the latest completed analysis.')
    payload = dict(result, reviewer=reviewer.strip(), video_id=video_id, run_id=run_id)
    times={result.get('evidence_timestamp_ms'),result.get('neutral_timestamp_ms'),result.get('current_timestamp_ms')}-{None}
    times.update(point['timestamp_ms'] for point in result.get('peak_evidence', []))
    payload['evidence_images']=[]
    artifacts=query(db,"SELECT path FROM analysis_artifacts WHERE run_id=? AND kind='per_frame_json'",(run_id,))
    if times and artifacts:
        for frame in load_frames(db,run_id):
            image_path=frame.get('source_frame_path')
            if frame['timestamp_ms'] in times and image_path and Path(image_path).exists():
                payload['evidence_images'].append({'timestamp_ms':frame['timestamp_ms'],'data_uri':'data:image/jpeg;base64,'+base64.b64encode(Path(image_path).read_bytes()).decode('ascii')})
    with transaction(db) as c:
        c.execute('INSERT INTO research_reviews VALUES(?,?,?,?,?,?)',(str(uuid.uuid4()),case_id,video_id,run_id,json.dumps(payload,allow_nan=False),now()))
        c.execute('UPDATE report_snapshots SET invalidated_at=? WHERE case_id=? AND invalidated_at IS NULL',(now(),case_id))


def manual_motion(neutral, current, points, fixed_camera, landmarks_verified, role='Lateral movement'):
    """Apparent image-plane change from two visible points in two source frames."""
    if role not in ('Lateral movement', 'Head flexion / extension'):
        raise ValueError('Manual two-frame movement review is supported only for lateral movement or flexion/extension.')
    if not fixed_camera or not landmarks_verified:
        raise ValueError('Confirm fixed camera and the same visible anatomical endpoints in both frames.')
    if neutral['timestamp_ms']==current['timestamp_ms']:
        raise ValueError('Choose two different frames.')
    if len(points)!=4: raise ValueError('Provide two endpoints per frame.')
    for point,frame in zip(points,[neutral,neutral,current,current]):
        x,y=point
        if not all(math.isfinite(v) for v in point) or not 0<=x<frame['source_width'] or not 0<=y<frame['source_height']:
            raise ValueError('Points must be inside their source frame.')
    if any(np.linalg.norm(np.asarray(points[i])-points[i+1])<10 for i in (0,2)):
        raise ValueError('Reference line must span at least 10 source pixels in each frame.')
    angle=relative_angle(line_angle_degrees(*points[:2]),line_angle_degrees(*points[2:]))
    return {'version':VERSION,'role':role,'state':'accepted','reasons':[],
            'method':'Reviewer-marked image-plane head-line change','points':points,
            'neutral_timestamp_ms':neutral['timestamp_ms'],'current_timestamp_ms':current['timestamp_ms'],
            'camera_fixed':True,'landmarks_verified':True,'findings':[{'metric':'manual_head_line_change',
            'label':'Apparent head-line change (torso compensation unknown)','value':angle,'unit':'degree',
            'timestamp_ms':current['timestamp_ms']}],
            'limitation':'Two-frame image-plane movement only; not full range or isolated neck motion.'}


def distance_result(value, uncertainty, method, reviewer, evidence):
    if not all(math.isfinite(v) for v in (value,uncertainty)) or value <= 0 or uncertainty < 0:
        raise ValueError('Distance must be positive; uncertainty must be finite and nonnegative.')
    if method not in ['Manual interincisor measurement','Calibrated incisor endpoints']:
        raise ValueError('Unsupported distance method')
    if not reviewer.strip() or not evidence.strip(): raise ValueError('Reviewer and measurement evidence are required')
    low, high = max(0,value-uncertainty),value+uncertainty
    status = 'Below reference threshold' if high < 3 else ('Threshold overlap — indeterminate' if low < 3 else 'Threshold not met')
    factor = (
        'Limited interincisor opening: clinician airway assessment factor present.'
        if status == 'Below reference threshold' else
        ('Interincisor opening overlaps the reference threshold: clinician review required.'
         if status.startswith('Threshold overlap') else
         'No limited interincisor-opening factor flagged by this reference comparison alone.')
    )
    return {'value':value,'unit':'cm','uncertainty_cm':uncertainty,'uncertainty_kind':'Reviewer-specified error bound, not a statistical confidence interval',
            'range_cm':[low,high],'threshold_cm':3.0,'comparison':'<','status':status,'method':method,
            'reviewer':reviewer.strip(),'evidence':evidence.strip(),'source':SOURCE,
            'factor_assessment':factor,
            'meaning':'Interincisor opening reference indicator; does not establish intubation outcome.'}


def save_distance(db, case_id, result):
    with transaction(db) as c:
        c.execute('INSERT INTO research_distances VALUES(?,?,?,?)',(str(uuid.uuid4()),case_id,json.dumps(result,allow_nan=False),now()))
        c.execute('UPDATE report_snapshots SET invalidated_at=? WHERE case_id=? AND invalidated_at IS NULL',(now(),case_id))


def case_report(db, case_id):
    clips = case_clips(db,case_id)
    output = []
    for clip in clips:
        run = latest_run(db,case_id,clip['id'])
        row = {'video_id':clip['id'],'file':clip['relative_path'],'source_hash':clip['sha256'],
               'run_id':run['id'] if run else None,'state':'not analyzed','reasons':['Analyze this clip'],'findings':[]}
        if run:
            reviews = query(db,'SELECT * FROM research_reviews WHERE case_id=? AND video_id=? AND run_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',(case_id,clip['id'],run['id']))
            row.update(state='needs review' if run['state']=='completed' else run['state'],reasons=['Review current run'] if run['state']=='completed' else [run.get('error') or run['state']])
            if reviews and run['state']=='completed': row.update(json.loads(reviews[0]['payload']))
        output.append(row)
    distances = query(db,'SELECT payload FROM research_distances WHERE case_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1',(case_id,))
    distance = json.loads(distances[0]['payload']) if distances else None
    accepted = sum(c['state']=='accepted' for c in output)
    conclusion = f'{accepted} of {len(output)} clips have accepted evidence.'
    if distance: conclusion += ' '+distance['factor_assessment']
    else: conclusion += ' Clinical threshold screening unavailable: a reviewer-entered physical interincisor measurement is required.'
    conclusion += ' Difficult-intubation prediction is not established by these measurements.'
    return {'version':VERSION,'case_id':case_id,'clips_expected':len(output),'clips_accepted':accepted,
            'status':'Review complete' if output and accepted==len(output) else 'More evidence needed',
            'clips':output,'distance_assessment':distance,'conclusion':conclusion,
            'quality_policy':POLICY,'limitations':['Quality cutoffs are engineering defaults and need validation.',
            'Different views and pixel scales are reported separately; no cross-view averaging.',
            'Lip aperture is distinct from the distance between incisor edges.',
            'Camera-relative motion is not an isolated anatomical neck range of motion.']}


def render_report(report):
    esc = lambda x: html.escape(str(x))
    parts = [f'<h1>Airway research report</h1><p>Case {esc(report["case_id"])}</p><h2>{esc(report["status"])}</h2><p>{esc(report["conclusion"])}</p>']
    for clip in report['clips']:
        parts.append(f'<h2>{esc(clip["file"])}</h2><p>{esc(clip["state"])} · {esc(clip.get("role","Unassigned"))}</p><p>{esc("; ".join(clip["reasons"]))}</p>')
        parts.append('<table><tr><th>Measurement</th><th>Value</th><th>Unit</th><th>Evidence time (ms)</th></tr>')
        for f in clip['findings']: parts.append(f'<tr><td>{esc(f["label"])}</td><td>{f["value"]:.3f}</td><td>{esc(f["unit"])}</td><td>{esc(f.get("timestamp_ms","interval"))}</td></tr>')
        parts.append(f'</table><p>Source SHA-256: {esc(clip["source_hash"])}<br>Run: {esc(clip["run_id"])}<br>Reviewer: {esc(clip.get("reviewer","Pending"))}</p>')
        for image in clip.get('evidence_images',[]):
            parts.append(f'<figure><img style="max-width:360px;width:100%" src="{esc(image["data_uri"])}"><figcaption>Source frame at {image["timestamp_ms"]:.0f} ms</figcaption></figure>')
    if report['distance_assessment']:
        d=report['distance_assessment']
        parts.append(f'<h2>Interincisor reference comparison</h2><p>{d["value"]:.2f} cm ± {d["uncertainty_cm"]:.2f} cm — {esc(d["status"])}</p><p>{esc(d["method"])} · {esc(d["evidence"])}</p><p>{esc(d["uncertainty_kind"])}</p><a href="{esc(d["source"])}">Reference: interincisor distance below 3 cm</a>')
    parts.append('<h2>Interpretation limits</h2><ul>'+''.join('<li>'+esc(s)+'</li>' for s in report['limitations'])+'</ul>')
    return '<!doctype html><html><head><meta charset="utf-8"><title>Airway research report</title><style>body{font:16px Segoe UI,sans-serif;color:#19354a;max-width:960px;margin:40px auto;padding:24px}h1{border-bottom:4px solid #197f82;padding-bottom:16px}table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:10px;border-bottom:1px solid #dae3eb}p{overflow-wrap:anywhere}@media print{body{margin:0}h2{break-after:avoid}}</style></head><body>'+''.join(parts)+'</body></html>'


def exports(report):
    serialized=json.dumps(report,indent=2,allow_nan=False,sort_keys=True)
    digest=hashlib.sha256(serialized.encode()).hexdigest()[:12]
    out=io.StringIO(); fields=['video_id','file','run_id','source_hash','role','state','reviewer','metric','value','unit','timestamp_ms','reason']
    writer=csv.DictWriter(out,fieldnames=fields);writer.writeheader()
    for clip in report['clips']:
        for finding in clip['findings'] or [{}]:
            row={k:clip.get(k,'') for k in fields};row.update({k:v for k,v in finding.items() if k in fields});row['reason']='; '.join(clip['reasons'])
            writer.writerow({k:("'"+str(v) if str(v).startswith(('=','+','-','@')) else v) for k,v in row.items()})
    d=report.get('distance_assessment')
    if d:
        row={'metric':'interincisor_distance','value':d['value'],'unit':'cm','state':d['status'],
             'reviewer':d['reviewer'],'reason':f"{d['method']}; error bound +/- {d['uncertainty_cm']} cm; < {d['threshold_cm']} cm reference; {d['evidence']}"}
        writer.writerow({k:("'"+str(v) if str(v).startswith(('=','+','-','@')) else v) for k,v in row.items()})
    return digest,{'html':render_report(report),'json':serialized,'csv':out.getvalue()}
