from __future__ import annotations

import hashlib, json, re, uuid
from pathlib import Path
from typing import Callable

def sha256_file(path: Path, chunk=1024*1024):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(chunk), b""): h.update(block)
    return h.hexdigest()

def stable_video_uuid(relative_path: str, sha256: str):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"airway-video:{relative_path}:{sha256}"))

def filename_timestamp(name: str):
    m=re.search(r"(\d{4}-\d{2}-\d{2}) at (\d{1,2}\.\d{2}\.\d{2}) ([AP]M)", name, re.I)
    return " ".join(m.groups()) if m else None

def decode_video(path: Path, *, contact_dir: Path|None=None, video_id: str|None=None, cancel: Callable[[],bool]|None=None):
    import av
    try: container=av.open(str(path))
    except Exception as exc: return {"decoder_version":"pyav-15.1-v1","status":"failed","error":f"open_failed:{type(exc).__name__}","frame_count":0,"presentation_timestamps_ms":[]}
    if not container.streams.video:
        container.close(); return {"decoder_version":"pyav-15.1-v1","status":"failed","error":"no_video_stream","frame_count":0,"presentation_timestamps_ms":[]}
    stream=container.streams.video[0]
    width=int(stream.codec_context.width or 0); height=int(stream.codec_context.height or 0)
    nominal=float(stream.average_rate) if stream.average_rate else 0.0; declared=int(stream.frames or 0)
    codec=stream.codec_context.name; rotation=int(stream.metadata.get("rotate","0") or 0)%360
    pts=[]; frames=[]; errors=[]; i=0; targets={max(0,int(declared*x)) for x in (.1,.5,.9)} if declared else {0}
    try:
        for frame in container.decode(stream):
            if cancel and cancel(): errors.append("cancelled"); break
            if i==0 and getattr(frame,"rotation",None) is not None: rotation=(-int(frame.rotation))%360
            t=float(frame.time*1000) if frame.time is not None else (float(frame.pts*frame.time_base*1000) if frame.pts is not None else None)
            pts.append(t)
            if i in targets: frames.append((i,t,frame.to_ndarray(format="bgr24")))
            i+=1
    except Exception as exc: errors.append(f"decode_error:{type(exc).__name__}:{exc}")
    has_audio=bool(container.streams.audio); container_name=container.format.name if container.format else path.suffix.lower().lstrip(".")
    container.close()
    if declared and i < declared: errors.append(f"decoded_{i}_of_declared_{declared}")
    known_pts=[t for t in pts if t is not None]; monotonic=all(b>=a for a,b in zip(known_pts,known_pts[1:]))
    if not monotonic: errors.append("non_monotonic_presentation_timestamps")
    status="failed" if i==0 else ("partial" if errors else "success")
    duration=(known_pts[-1] if known_pts else 0.0) + (1000/nominal if nominal>0 else 0)
    contacts=[]
    if contact_dir and frames:
        import cv2
        contact_dir.mkdir(parents=True,exist_ok=True)
        for n,t,frame in frames:
            out=contact_dir/f"{video_id}_{n}.jpg"; cv2.imwrite(str(out),frame); contacts.append({"frame":n,"timestamp_ms":t,"path":str(out)})
    return {"decoder_version":"pyav-15.1-v1","status":status,"error":";".join(errors) or None,"container":container_name,"codec":codec or None,
            "duration_ms":duration,"width":width,"height":height,"aspect_ratio":width/height if height else None,
            "rotation_metadata_degrees":rotation,"nominal_fps":nominal or None,"average_fps":((len(known_pts)-1)*1000/(known_pts[-1]-known_pts[0])) if len(known_pts)>1 and known_pts[-1]>known_pts[0] else nominal or None,
            "frame_count":i,"declared_frame_count":declared or None,"presentation_timestamps_ms":pts,"timestamps_monotonic":monotonic,
            "first_access_ms":pts[0] if pts else None,"middle_access_ms":pts[len(pts)//2] if pts else None,"end_access_ms":pts[-1] if pts else None,
            "audio_present":has_audio,"audio_note":None,"contact_frames":contacts}

def json_dump_strict(data, path: Path):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
    tmp.replace(path)
