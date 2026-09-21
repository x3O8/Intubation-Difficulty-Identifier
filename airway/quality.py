from __future__ import annotations
import numpy as np

def frame_quality(frame):
    import cv2
    gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
    return {"laplacian_variance":float(cv2.Laplacian(gray,cv2.CV_64F).var()),
            "dark_fraction":float(np.mean(gray<=10)),"clipped_fraction":float(np.mean(gray>=245)),
            "width":int(frame.shape[1]),"height":int(frame.shape[0])}

def evidence_state(*, readable=True,maneuver=True,anatomy=True,calibration=True,protocol=True,multiple_faces=False):
    reasons=[]
    if not readable: reasons.append("unreadable_media")
    if not maneuver: reasons.append("missing_maneuver")
    if not anatomy: reasons.append("anatomy_not_visible")
    if not calibration: reasons.append("missing_calibration")
    if not protocol: reasons.append("protocol_mismatch")
    if multiple_faces: reasons.append("multiple_faces")
    return ("available",[]) if not reasons else ("unavailable",reasons)
