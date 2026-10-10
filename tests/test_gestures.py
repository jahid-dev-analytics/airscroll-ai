import pytest

from airscroll.gestures import Pose, classify_pose, palm_size
from tests.handgen import make_hand

CASES = [
    ("open_palm", Pose.OPEN_PALM),
    ("fist", Pose.FIST),
    ("thumb_up", Pose.THUMB_UP),
    ("peace", Pose.PEACE),
    ("pointing", Pose.ONE_FINGER),
    ("three", Pose.OTHER),
]


@pytest.mark.parametrize("shape,expected", CASES)
def test_basic_poses(shape, expected):
    assert classify_pose(make_hand(shape)) == expected


@pytest.mark.parametrize("shape,expected", [c for c in CASES if c[0] != "thumb_up"])
@pytest.mark.parametrize("angle", [-30, -15, 15, 30])
def test_poses_survive_hand_tilt(shape, expected, angle):
    assert classify_pose(make_hand(shape, angle_deg=angle)) == expected


@pytest.mark.parametrize("shape,expected", CASES)
@pytest.mark.parametrize("scale", [0.06, 0.15, 0.35])
def test_poses_independent_of_distance_to_camera(shape, expected, scale):
    assert classify_pose(make_hand(shape, scale=scale)) == expected


@pytest.mark.parametrize("shape,expected", CASES)
def test_poses_tolerate_landmark_jitter(shape, expected):
    # 0.002 image units ~ the jitter MediaPipe shows on a steady hand
    hits = sum(
        classify_pose(make_hand(shape, noise=0.002, seed=i)) == expected for i in range(50)
    )
    assert hits >= 45


def test_tilted_thumb_up_still_counts():
    assert classify_pose(make_hand("thumb_up", angle_deg=10)) == Pose.THUMB_UP


def test_upside_down_thumb_is_not_a_like():
    # thumb pointing down must never be read as a like
    assert classify_pose(make_hand("thumb_up", angle_deg=180)) != Pose.THUMB_UP


def test_missing_or_partial_hand():
    assert classify_pose(None) == Pose.NONE
    assert classify_pose(make_hand()[:10]) == Pose.NONE


def test_palm_size_scales():
    assert palm_size(make_hand(scale=0.3)) == pytest.approx(2 * palm_size(make_hand(scale=0.15)))
