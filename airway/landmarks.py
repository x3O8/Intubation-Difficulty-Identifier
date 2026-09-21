from __future__ import annotations
from pathlib import Path
import hashlib

MODEL_PATH=Path("models/face_landmarker.task")
POSE_MODEL_PATH=Path("models/pose_landmarker_lite.task")

# MediaPipe Face Landmarker topology (478-point task model). These semantic
# anchors are versioned here and are deliberately limited to visible features.
LANDMARK_MAP_VERSION = "mediapipe-face-landmarker-478-v1"
LANDMARK_IDS = {
    "left_mouth_corner": 61,
    "right_mouth_corner": 291,
    "upper_inner_lip": 13,
    "lower_inner_lip": 14,
    "left_outer_eye": 33,
    "right_outer_eye": 263,
}

def model_sha256(path=MODEL_PATH):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""): h.update(block)
    return h.hexdigest()

def profile_pose(result):
    poses=result.pose_landmarks or []
    if len(poses)!=1 or len(poses[0])<=12: return {"valid":False,"reason":"pose_not_detected"}
    nose,left,right=poses[0][0],poses[0][11],poses[0][12]
    confidence=min(getattr(p,"visibility",0.0) for p in (nose,left,right))
    if confidence<.4: return {"valid":False,"reason":"pose_landmarks_low_visibility","confidence":float(confidence)}
    sx,sy=(left.x+right.x)/2,(left.y+right.y)/2
    import math
    return {"valid":True,"method":"pose_shoulder_to_nose_image_plane","confidence":float(confidence),"head_line_angle_degrees":float(math.degrees(math.atan2(nose.y-sy,nose.x-sx))),"nose":[float(nose.x),float(nose.y)],"shoulder_midpoint":[float(sx),float(sy)]}

class FaceLandmarkerAdapter:
    """Local VIDEO-mode adapter. It never downloads a model at runtime."""
    def __init__(self, model_path=MODEL_PATH):
        self.model_path=Path(model_path); self._detector=None; self._last_ms=-1
        if not self.model_path.exists():
            raise FileNotFoundError(f"Missing local model: {self.model_path}. Run scripts/setup.ps1 with an approved model file.")
        import mediapipe as mp
        opts=mp.tasks.vision.FaceLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(self.model_path)),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,num_faces=2,
            output_face_blendshapes=False,output_facial_transformation_matrixes=True)
        self._detector=mp.tasks.vision.FaceLandmarker.create_from_options(opts)
    def detect(self, rgb_array, timestamp_ms):
        if timestamp_ms<=self._last_ms: raise ValueError("timestamps must increase within one clip; reset between clips/cuts")
        import mediapipe as mp
        self._last_ms=timestamp_ms
        return self._detector.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB,data=rgb_array),int(timestamp_ms))
    def __enter__(self): return self
    def __exit__(self, *_): self.close()
    def close(self):
        if self._detector: self._detector.close()

class PoseLandmarkerAdapter:
    def __init__(self, model_path=POSE_MODEL_PATH):
        self.model_path=Path(model_path); self._detector=None; self._last_ms=-1
        if not self.model_path.exists(): raise FileNotFoundError(f"Missing local pose model: {self.model_path}")
        import mediapipe as mp
        opts=mp.tasks.vision.PoseLandmarkerOptions(base_options=mp.tasks.BaseOptions(model_asset_path=str(self.model_path)),running_mode=mp.tasks.vision.RunningMode.VIDEO,num_poses=1,min_pose_detection_confidence=.3,min_pose_presence_confidence=.3,min_tracking_confidence=.3)
        self._detector=mp.tasks.vision.PoseLandmarker.create_from_options(opts)
    def detect(self,rgb_array,timestamp_ms):
        if timestamp_ms<=self._last_ms: raise ValueError("timestamps must increase within one clip")
        import mediapipe as mp
        self._last_ms=timestamp_ms
        return self._detector.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB,data=rgb_array),int(timestamp_ms))
    def __enter__(self): return self
    def __exit__(self,*_): self.close()
    def close(self):
        if self._detector: self._detector.close()
