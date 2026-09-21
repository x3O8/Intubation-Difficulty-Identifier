import numpy as np
import pytest
from airway.geometry import rotation_transform, resize_letterbox, crop_transform
from airway.measurements import ratio_distance, relative_angle, closest_rotation, relative_rotation, euler_zyx_degrees

@pytest.mark.parametrize("degrees",[0,90,180,270])
def test_rotation_round_trip(degrees):
    p=np.array([[0.25,1.75],[50.5,99.25],[199.0,149.0]])
    t=rotation_transform(200,150,degrees)
    assert np.max(np.abs(t.inverse().apply(t.apply(p))-p)) < .5

def test_crop_resize_round_trip():
    p=np.array([[30.2,40.3],[100.1,90.4]])
    t=crop_transform(10,20).then(resize_letterbox(180,120,640,480,source="crop",target="display"))
    assert np.max(np.abs(t.inverse().apply(t.apply(p))-p)) < .5

def test_uniform_resize_ratio_within_one_percent():
    p=[(10,10),(10,30),(0,0),(40,0)]
    r1=ratio_distance(*p); r2=ratio_distance(*[(x*4,y*4) for x,y in p])
    assert abs(r1-r2)/r1 < .01

@pytest.mark.parametrize("angle",[0,10,20])
def test_synthetic_motion_preserved(angle):
    assert abs(relative_angle(0,angle)-angle) < 1

def test_svd_rotation_removes_scale_and_reports_yaw():
    a=np.radians(20); r=np.array([[np.cos(a),0,np.sin(a)],[0,1,0],[-np.sin(a),0,np.cos(a)]])
    recovered=closest_rotation(r@np.diag([1.02,.98,1.01]))
    assert np.linalg.det(recovered)==pytest.approx(1,abs=1e-6)
    assert euler_zyx_degrees(relative_rotation(np.eye(3),recovered))["yaw"]==pytest.approx(20,abs=.5)

def test_invalid_pose_matrix_rejected():
    with pytest.raises(ValueError): closest_rotation(np.full((3,3),np.nan))
