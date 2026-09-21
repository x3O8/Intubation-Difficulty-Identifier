from __future__ import annotations
import math
import numpy as np

def distance(a, b):
    return float(np.linalg.norm(np.asarray(a, float)-np.asarray(b, float)))

def ratio_distance(a, b, c, d):
    den = distance(c, d)
    if den <= 0: raise ValueError("ratio denominator must be positive")
    return distance(a, b) / den

def line_angle_degrees(a, b):
    x, y = np.asarray(b, float)-np.asarray(a, float)
    return math.degrees(math.atan2(y, x))

def relative_angle(neutral, current):
    return (current-neutral+180.0)%360.0-180.0

def json_number(value):
    if value is None: return None
    v = float(value)
    if not math.isfinite(v): raise ValueError("NaN and Infinity are not permitted")
    return v

def closest_rotation(matrix):
    """Remove scale/shear from a 3x3 block using SVD and correct reflection."""
    a=np.asarray(matrix,float)
    if a.shape != (3,3) or not np.isfinite(a).all(): raise ValueError("invalid rotation block")
    u,_,vt=np.linalg.svd(a); r=u@vt
    if np.linalg.det(r)<0:
        u[:,-1]*=-1; r=u@vt
    if np.linalg.det(r)<0.999 or np.linalg.det(r)>1.001: raise ValueError("unstable rotation")
    return r

def relative_rotation(neutral, current):
    return closest_rotation(current) @ closest_rotation(neutral).T

def euler_zyx_degrees(rotation):
    """Return camera-coordinate yaw(Y), pitch(X), roll(Z), intrinsic ZYX."""
    r=closest_rotation(rotation)
    sy=float(np.hypot(r[0,0],r[1,0]))
    if sy>1e-8:
        x=np.arctan2(r[2,1],r[2,2]); y=np.arctan2(-r[2,0],sy); z=np.arctan2(r[1,0],r[0,0])
    else:
        x=np.arctan2(-r[1,2],r[1,1]); y=np.arctan2(-r[2,0],sy); z=0.0
    return {"yaw":float(np.degrees(y)),"pitch":float(np.degrees(x)),"roll":float(np.degrees(z))}

def robust_summary(values):
    a=np.asarray([x for x in values if x is not None and np.isfinite(x)],float)
    if not len(a): return None
    return {"minimum":float(a.min()),"maximum":float(a.max()),"p05":float(np.percentile(a,5)),
            "p95":float(np.percentile(a,95)),"robust_excursion_p95_minus_p05":float(np.percentile(a,95)-np.percentile(a,5)),"count":int(len(a))}
