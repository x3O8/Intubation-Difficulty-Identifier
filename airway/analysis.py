from __future__ import annotations

import hashlib, json, uuid
from pathlib import Path
from typing import Callable

import numpy as np

from .db import transaction
from .geometry import orient_frame
from .ingest import now, ensure_under_managed
from .landmarks import (FaceLandmarkerAdapter, PoseLandmarkerAdapter, LANDMARK_IDS,
    LANDMARK_MAP_VERSION, POSE_MODEL_PATH, model_sha256, profile_pose)
from .measurements import distance, euler_zyx_degrees, relative_rotation, robust_summary
from .prototype import relative_opening_band
from .quality import frame_quality
from .video import json_dump_strict

ALGORITHM_VERSION="pretrained-landmark-mvp-3.0"

def _hash(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def _rotation(metadata):
    try: return int(json.loads(metadata or "{}").get("rotation_metadata_degrees",0))%360
    except Exception: return 0

def _draw_overlay(bgr, points):
    import cv2
    out=bgr.copy()
    # A sparse but readable topology verification overlay plus metric anchors.
    for x,y in points[::4]: cv2.circle(out,(int(round(x)),int(round(y))),1,(65,220,175),-1)
    colors={"upper_inner_lip":(0,220,255),"lower_inner_lip":(0,220,255),"left_mouth_corner":(255,180,0),"right_mouth_corner":(255,180,0),"left_outer_eye":(255,90,210),"right_outer_eye":(255,90,210)}
    for name,idx in LANDMARK_IDS.items():
        x,y=points[idx]; cv2.circle(out,(int(round(x)),int(round(y))),4,colors[name],-1); cv2.putText(out,str(idx),(int(x)+4,int(y)-4),cv2.FONT_HERSHEY_SIMPLEX,.38,colors[name],1,cv2.LINE_AA)
    return out

def _frame_record(result, width, height, timestamp_ms, quality):
    faces=result.face_landmarks or []
    rec={"timestamp_ms":float(timestamp_ms),"face_count":len(faces),"valid":False,"reason_codes":[],"quality":quality,"landmarks":None,"matrix":None}
    if len(faces)!=1:
        rec["reason_codes"].append("multiple_faces" if len(faces)>1 else "face_not_detected"); return rec
    pts=np.array([[p.x*width,p.y*height,p.z] for p in faces[0]],float)
    if len(pts)<=max(LANDMARK_IDS.values()): rec["reason_codes"].append("unexpected_landmark_topology"); return rec
    xy=pts[:,:2]; chosen=xy[list(LANDMARK_IDS.values())]
    if not np.isfinite(chosen).all() or np.any(chosen[:,0]<0) or np.any(chosen[:,0]>=width) or np.any(chosen[:,1]<0) or np.any(chosen[:,1]>=height):
        rec["reason_codes"].append("metric_endpoint_out_of_frame"); return rec
    p={name:xy[idx].tolist() for name,idx in LANDMARK_IDS.items()}
    aperture=distance(p["upper_inner_lip"],p["lower_inner_lip"]); mouth=distance(p["left_mouth_corner"],p["right_mouth_corner"]); eyes=distance(p["left_outer_eye"],p["right_outer_eye"])
    rec.update({"valid":True,"landmarks":pts.tolist(),"visible_lip_aperture_px":aperture,"mouth_width_px":mouth,
                "lip_aperture_over_mouth_width":aperture/mouth if mouth>0 else None,
                "lip_aperture_over_outer_eye_span":aperture/eyes if eyes>0 else None})
    mats=result.facial_transformation_matrixes or []
    if mats:
        m=np.asarray(mats[0],float)
        if m.shape==(4,4) and np.isfinite(m).all(): rec["matrix"]=m.tolist()
        else: rec["reason_codes"].append("unstable_pose_matrix")
    else: rec["reason_codes"].append("pose_matrix_missing")
    return rec

def analyze_clip(case_id, video_id, *, sample_hz=10.0, db_path="data/airway.sqlite3", model_path="models/face_landmarker.task", pose_model_path=POSE_MODEL_PATH, cancel:Callable[[],bool]|None=None, progress:Callable[[float],None]|None=None):
    import av, cv2
    if sample_hz<=0: raise ValueError("sample_hz must be positive")
    with transaction(db_path) as c:
        video=c.execute("SELECT * FROM videos WHERE id=?",(video_id,)).fetchone()
    if not video: raise ValueError("video not found")
    source=Path(video["source_path"]); mh=model_sha256(model_path); pose_hash=model_sha256(pose_model_path); run_id=str(uuid.uuid4())
    if _hash(source)!=video['sha256']:
        raise ValueError('Source video changed since inventory. Re-import the source before analysis.')
    config={"sample_hz":sample_hz,"timestamp_source":"PyAV frame PTS/time_base","num_faces":2,"landmark_map_version":LANDMARK_MAP_VERSION,"pose_model":Path(pose_model_path).stem,"pose_model_sha256":pose_hash,"profile_angle_coordinate_space":"source_pixels_v1","algorithm_version":ALGORITHM_VERSION,"source_rotation_degrees":_rotation(video["metadata_json"])}
    with transaction(db_path) as c:
        c.execute("INSERT INTO analysis_runs(id,case_id,video_id,config_json,model_hash,state,started_at) VALUES(?,?,?,?,?,?,?)",(run_id,case_id,video_id,json.dumps(config),mh,"running",now()))
    root=ensure_under_managed(Path("data/runs")/run_id,"data"); root.mkdir(parents=True,exist_ok=True); thumbs=root/"thumbnails"; thumbs.mkdir()
    records=[]; duplicate_ms=[]; sampled=0; decoded=0; next_t=None; last_ms=-1
    container=None
    try:
        container=av.open(str(source)); stream=container.streams.video[0]
        duration=float(stream.duration*stream.time_base*1000) if stream.duration is not None else None
        with FaceLandmarkerAdapter(model_path) as detector, PoseLandmarkerAdapter(pose_model_path) as pose_detector:
            for frame in container.decode(stream):
                decoded+=1
                if cancel and cancel(): raise InterruptedError("cancelled")
                if frame.time is None and frame.pts is None: continue
                t=float(frame.time*1000 if frame.time is not None else frame.pts*frame.time_base*1000)
                if next_t is None: next_t=t
                if t+1e-6<next_t: continue
                next_t += 1000.0/sample_hz
                ms=int(round(t))
                if ms<=last_ms:
                    duplicate_ms.append({"timestamp_ms":t,"rounded_ms":ms}); continue
                last_ms=ms
                # PyAV exposes container display-matrix rotation on decoded frames;
                # it is authoritative when the simpler stream metadata tag is absent.
                # FFmpeg reports display-matrix rotation with the opposite sign
                # to the pixel operation needed to present an upright frame.
                display_rotation=getattr(frame,"rotation",None)
                frame_rotation=(-int(display_rotation))%360 if display_rotation is not None else config["source_rotation_degrees"]
                if sampled==0: config["source_rotation_degrees"]=frame_rotation
                bgr=orient_frame(frame.to_ndarray(format="bgr24"),frame_rotation); h,w=bgr.shape[:2]
                rgb=cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB)
                result=detector.detect(rgb,ms)
                pose_result=pose_detector.detect(rgb,ms)
                rec=_frame_record(result,w,h,t,frame_quality(bgr)); rec["sample_index"]=sampled; rec["source_width"]=w; rec["source_height"]=h
                rec["profile_pose"]=profile_pose(pose_result,w,h)
                original=thumbs/f"source_{sampled:06d}_{ms}.jpg"
                cv2.imwrite(str(original),bgr);rec['source_frame_path']=str(original)
                if rec["valid"] and (sampled%max(1,int(round(sample_hz)))==0):
                    op=thumbs/f"{sampled:06d}_{ms}.jpg"; cv2.imwrite(str(op),_draw_overlay(bgr,np.asarray(rec["landmarks"])[:,:2])); rec["overlay_path"]=str(op)
                records.append(rec); sampled+=1
                if progress and duration: progress(min(1.0,t/duration))
        container.close()
        raw={"schema_version":"1.0","run_id":run_id,"video_id":video_id,"source_sha256":video["sha256"],"model_sha256":mh,"configuration":config,"duplicate_millisecond_timestamps":duplicate_ms,"frames":records}
        raw_path=root/"frames.json"; json_dump_strict(raw,raw_path)
        valid=[r for r in records if r["valid"]]; coverage=len(valid)/len(records) if records else 0.0
        pose_valid=[r for r in records if r.get("profile_pose",{}).get("valid")]
        summary={"sampled_frames":len(records),"valid_single_face_frames":len(valid),"tracking_coverage":coverage,"profile_pose_frames":len(pose_valid),"profile_pose_coverage":len(pose_valid)/len(records) if records else 0.0,"sampling_hz_target":sample_hz,"duplicate_timestamps_dropped":len(duplicate_ms),"gap_locations_ms":[r["timestamp_ms"] for r in records if not r["valid"]],"metrics":{}}
        for key in ("visible_lip_aperture_px","mouth_width_px","lip_aperture_over_mouth_width","lip_aperture_over_outer_eye_span"):
            summary["metrics"][key]=robust_summary([r.get(key) for r in valid])
        prototype_ratio=(summary["metrics"].get("lip_aperture_over_mouth_width") or {}).get("maximum")
        summary["prototype_relative_opening_band"]=relative_opening_band(prototype_ratio)
        summary_path=root/"summary.json"; json_dump_strict(summary,summary_path)
        with transaction(db_path) as c:
            c.execute("UPDATE measurements SET active=0 WHERE case_id=? AND video_id=?",(case_id,video_id))
            c.execute("UPDATE report_snapshots SET invalidated_at=? WHERE case_id=? AND invalidated_at IS NULL",(now(),case_id))
            for kind,path in (("per_frame_json",raw_path),("summary_json",summary_path)):
                c.execute("INSERT INTO analysis_artifacts VALUES(?,?,?,?,?,?,?)",(str(uuid.uuid4()),run_id,kind,str(path),_hash(path),"{}",now()))
            for metric,key,unit in (("visible_lip_aperture","visible_lip_aperture_px","px"),("mouth_width","mouth_width_px","px"),("lip_aperture_mouth_width_ratio","lip_aperture_over_mouth_width","ratio"),("lip_aperture_eye_span_ratio","lip_aperture_over_outer_eye_span","ratio"),("prototype_relative_opening_index","lip_aperture_over_mouth_width","ratio"),("tracking_coverage",None,"ratio")):
                val=coverage if key is None else ((summary["metrics"].get(key) or {}).get("maximum"))
                payload={"summary":summary["metrics"].get(key) if key else summary,"requires_reviewer_interval":metric!="tracking_coverage"}
                if metric=="prototype_relative_opening_index": payload["display_band"]=relative_opening_band(val); payload["limitation"]="Display-only proof-of-concept heuristic; not centimetres, a physical measurement, or a clinical threshold."
                c.execute("INSERT INTO proposals VALUES(?,?,?,?,?,?)",(str(uuid.uuid4()),run_id,metric,json.dumps(payload,allow_nan=False),"needs_review" if metric!="tracking_coverage" else "available",now()))
                c.execute("INSERT INTO measurements(id,case_id,video_id,run_id,metric_id,metric_version,source_hash,value,unit,coordinate_space,method,quality_json,state,reason_codes_json,revised_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(str(uuid.uuid4()),case_id,video_id,run_id,metric,"1.0",video["sha256"],val,unit,"orientation_corrected_source_pixels" if unit=="px" else "dimensionless",ALGORITHM_VERSION,json.dumps({"tracking_coverage":coverage}),"available" if metric=="tracking_coverage" else "needs_review",json.dumps([] if valid else ["no_valid_single_face_frames"]),now()))
            for metric,reason in (("interincisor_distance","face_landmarks_do_not_identify_incisal_edges"),("upper_lip_bite_class","tooth_relationship_not_supported"),("clinical_anthropometry","landmarks_or_physical_scale_not_supported"),("cormack_lehane","requires_internal_laryngeal_view"),("pogo","requires_internal_laryngeal_view"),("centimetre_thresholds","no_valid_physical_calibration")):
                c.execute("INSERT INTO measurements(id,case_id,video_id,run_id,metric_id,metric_version,source_hash,method,state,reason_codes_json,revised_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(str(uuid.uuid4()),case_id,video_id,run_id,metric,"1.0",video["sha256"],ALGORITHM_VERSION,"not_applicable" if metric in ("cormack_lehane","pogo") else "unavailable",json.dumps([reason]),now()))
            c.execute("UPDATE analysis_runs SET state='completed',completed_at=?,config_json=? WHERE id=?",(now(),json.dumps(config),run_id))
        return {"run_id":run_id,"summary":summary,"raw_path":str(raw_path),"summary_path":str(summary_path)}
    except Exception as exc:
        with transaction(db_path) as c: c.execute("UPDATE analysis_runs SET state=?,completed_at=?,error=? WHERE id=?",("cancelled" if isinstance(exc,InterruptedError) else "failed",now(),f"{type(exc).__name__}: {exc}",run_id))
        raise

    finally:
        if container is not None: container.close()

def review_intervals(run_id, reviewer, neutral, maneuver, exclusions, camera_fixed, *, db_path="data/airway.sqlite3"):
    with transaction(db_path) as c:
        run=c.execute("SELECT * FROM analysis_runs WHERE id=? AND state='completed'",(run_id,)).fetchone()
        art=c.execute("SELECT path FROM analysis_artifacts WHERE run_id=? AND kind='per_frame_json'",(run_id,)).fetchone()
    if not run or not art: raise ValueError("completed run artifact not found")
    ns,ne=map(float,neutral); ms,me=map(float,maneuver)
    if not (ns<=ne and ms<=me): raise ValueError("interval start must not exceed end")
    raw=json.loads(Path(art["path"]).read_text(encoding="utf-8")); frames=raw["frames"]
    valid=[f for f in frames if f["valid"] and not any(a<=f["timestamp_ms"]<=b for a,b in exclusions)]
    neutral_frames=[f for f in valid if ns<=f["timestamp_ms"]<=ne and f.get("matrix")]
    maneuver_frames=[f for f in valid if ms<=f["timestamp_ms"]<=me]
    if not neutral_frames: raise ValueError("neutral interval must contain a valid pose frame")
    rotations=[np.asarray(f["matrix"],float)[:3,:3] for f in neutral_frames]
    neutral_r=np.mean(rotations,axis=0)
    pose=[]
    for f in maneuver_frames:
        if not f.get("matrix"): continue
        try: pose.append({"timestamp_ms":f["timestamp_ms"],**euler_zyx_degrees(relative_rotation(neutral_r,np.asarray(f["matrix"],float)[:3,:3]))})
        except ValueError: pass
    fixed=camera_fixed=="yes"
    result={"neutral_interval_ms":[ns,ne],"maneuver_interval_ms":[ms,me],"excluded_intervals_ms":exclusions,"camera_fixed":camera_fixed,"frame_count":len(maneuver_frames),"pose_available":fixed and bool(pose),"pose_skip_reason":None if fixed and pose else ("camera_not_confirmed_fixed" if not fixed else "no_stable_pose_matrices"),"metrics":{}}
    for key in ("visible_lip_aperture_px","mouth_width_px","lip_aperture_over_mouth_width","lip_aperture_over_outer_eye_span"):
        result["metrics"][key]=robust_summary([f.get(key) for f in maneuver_frames])
    ratio_summary=result["metrics"].get("lip_aperture_over_mouth_width") or {}
    result["prototype_relative_opening_band"]=relative_opening_band(ratio_summary.get("maximum"))
    if fixed and pose:
        result["relative_pose_degrees"]={axis:robust_summary([p[axis] for p in pose]) for axis in ("yaw","pitch","roll")}; result["pose_series"]=pose
    rid=str(uuid.uuid4())
    with transaction(db_path) as c:
        c.execute("UPDATE review_intervals SET active=0 WHERE run_id=?",(run_id,))
        c.execute("INSERT INTO review_intervals VALUES(?,?,?,?,?,?,?,?,?,?,1)",(rid,run_id,reviewer,ns,ne,ms,me,json.dumps(exclusions),camera_fixed,now()))
        for metric,key,unit in (("visible_lip_aperture","visible_lip_aperture_px","px"),("mouth_width","mouth_width_px","px"),("lip_aperture_mouth_width_ratio","lip_aperture_over_mouth_width","ratio"),("lip_aperture_eye_span_ratio","lip_aperture_over_outer_eye_span","ratio")):
            s=result["metrics"].get(key); c.execute("UPDATE measurements SET active=0 WHERE run_id=? AND metric_id=? AND active=1",(run_id,metric))
            c.execute("INSERT INTO measurements(id,case_id,video_id,run_id,metric_id,metric_version,source_hash,interval_json,value,unit,coordinate_space,method,quality_json,state,reason_codes_json,reviewer,revised_at,active) SELECT ?,r.case_id,r.video_id,r.id,?,'1.0',v.sha256,?,?,?,?,?,?,?,?,?,?,1 FROM analysis_runs r JOIN videos v ON v.id=r.video_id WHERE r.id=?",(str(uuid.uuid4()),metric,json.dumps(result),s["maximum"] if s else None,unit,"orientation_corrected_source_pixels" if unit=="px" else "dimensionless",ALGORITHM_VERSION,json.dumps({"reviewed_frame_count":len(maneuver_frames)}),"available" if s else "unavailable",json.dumps([] if s else ["no_eligible_frames_in_interval"]),reviewer,now(),run_id))
        s=result["metrics"].get("lip_aperture_over_mouth_width")
        c.execute("UPDATE measurements SET active=0 WHERE run_id=? AND metric_id='prototype_relative_opening_index' AND active=1",(run_id,))
        c.execute("INSERT INTO measurements(id,case_id,video_id,run_id,metric_id,metric_version,source_hash,interval_json,value,unit,coordinate_space,method,quality_json,state,reason_codes_json,reviewer,revised_at,active) SELECT ?,r.case_id,r.video_id,r.id,'prototype_relative_opening_index','1.0',v.sha256,?,?,?,?,?,?,?,?,?,?,1 FROM analysis_runs r JOIN videos v ON v.id=r.video_id WHERE r.id=?",(str(uuid.uuid4()),json.dumps(result),s["maximum"] if s else None,"ratio","dimensionless",ALGORITHM_VERSION,json.dumps({"display_band":result["prototype_relative_opening_band"],"limitation":"Display-only proof-of-concept heuristic; not centimetres, a physical measurement, or a clinical threshold."}),"available" if s else "unavailable",json.dumps(["proof_of_concept_display_only"] if s else ["no_eligible_frames_in_interval"]),reviewer,now(),run_id))
        for axis in ("yaw","pitch","roll"):
            metric=f"relative_head_{axis}"; s=(result.get("relative_pose_degrees") or {}).get(axis); c.execute("UPDATE measurements SET active=0 WHERE run_id=? AND metric_id=? AND active=1",(run_id,metric))
            c.execute("INSERT INTO measurements(id,case_id,video_id,run_id,metric_id,metric_version,source_hash,interval_json,value,unit,coordinate_space,method,quality_json,state,reason_codes_json,reviewer,revised_at,active) SELECT ?,r.case_id,r.video_id,r.id,?,'1.0',v.sha256,?,?,?,?,?,?,?,?,?,?,1 FROM analysis_runs r JOIN videos v ON v.id=r.video_id WHERE r.id=?",(str(uuid.uuid4()),metric,json.dumps(result),s["robust_excursion_p95_minus_p05"] if s else None,"degree","camera_coordinates_intrinsic_ZYX",ALGORITHM_VERSION,"{}","available" if s else "unavailable",json.dumps([] if s else [result["pose_skip_reason"]]),reviewer,now(),run_id))
        c.execute("UPDATE report_snapshots SET invalidated_at=? WHERE case_id=(SELECT case_id FROM analysis_runs WHERE id=?) AND invalidated_at IS NULL",(now(),run_id))
    return result
