from __future__ import annotations

from dataclasses import dataclass
import numpy as np

@dataclass(frozen=True)
class Transform:
    source_space: str
    target_space: str
    matrix: np.ndarray

    def __post_init__(self):
        m = np.asarray(self.matrix, dtype=float)
        if m.shape != (3, 3) or not np.isfinite(m).all() or abs(np.linalg.det(m)) < 1e-12:
            raise ValueError("transform must be a finite invertible 3x3 matrix")
        object.__setattr__(self, "matrix", m)

    def apply(self, points):
        p = np.asarray(points, dtype=float)
        h = np.c_[p, np.ones(len(p))]
        out = (self.matrix @ h.T).T
        return out[:, :2] / out[:, 2:3]

    def inverse(self):
        return Transform(self.target_space, self.source_space, np.linalg.inv(self.matrix))

    def then(self, other: "Transform"):
        if self.target_space != other.source_space:
            raise ValueError("coordinate spaces do not join")
        return Transform(self.source_space, other.target_space, other.matrix @ self.matrix)

def rotation_transform(width: int, height: int, degrees: int, source="encoded", target="source"):
    d = degrees % 360
    mats = {
        0: np.eye(3),
        90: np.array([[0,-1,height-1],[1,0,0],[0,0,1]], float),
        180: np.array([[-1,0,width-1],[0,-1,height-1],[0,0,1]], float),
        270: np.array([[0,1,0],[-1,0,width-1],[0,0,1]], float),
    }
    if d not in mats: raise ValueError("rotation must be 0/90/180/270")
    return Transform(source, target, mats[d])

def oriented_size(width:int,height:int,degrees:int):
    return (height,width) if degrees%360 in (90,270) else (width,height)

def orient_frame(frame, degrees:int):
    import cv2
    d=degrees%360
    if d==0: return frame
    if d==90: return cv2.rotate(frame,cv2.ROTATE_90_CLOCKWISE)
    if d==180: return cv2.rotate(frame,cv2.ROTATE_180)
    if d==270: return cv2.rotate(frame,cv2.ROTATE_90_COUNTERCLOCKWISE)
    raise ValueError("rotation must be 0/90/180/270")

def resize_letterbox(src_w, src_h, dst_w, dst_h, source="source", target="display"):
    scale = min(dst_w/src_w, dst_h/src_h)
    tx, ty = (dst_w-src_w*scale)/2, (dst_h-src_h*scale)/2
    return Transform(source, target, np.array([[scale,0,tx],[0,scale,ty],[0,0,1]], float))

def crop_transform(x, y, source="source", target="crop"):
    return Transform(source, target, np.array([[1,0,-x],[0,1,-y],[0,0,1]], float))

def physical_distance(target_px: float, reference_px: float, reference_cm: float) -> float:
    if reference_px <= 0 or reference_cm <= 0: raise ValueError("verified positive calibration required")
    return target_px * reference_cm / reference_px
