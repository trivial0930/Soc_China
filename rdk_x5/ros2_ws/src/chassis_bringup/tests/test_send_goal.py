import math
import pytest
from chassis_bringup.send_goal import parse_pose, build_parser


def test_parse_pose_none_returns_none():
    assert parse_pose(None) is None


def test_parse_pose_triple():
    assert parse_pose([1.0, 2.0, 0.5]) == (1.0, 2.0, 0.5)


def test_parse_pose_casts_ints():
    assert parse_pose([1, 2, 0]) == (1.0, 2.0, 0.0)


def test_parse_pose_bad_length_raises():
    with pytest.raises(ValueError):
        parse_pose([1.0, 2.0])


def test_parser_requires_goal():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_parser_goal_only():
    args = build_parser().parse_args(["--goal", "1.5", "0", "0"])
    assert args.goal == [1.5, 0.0, 0.0]
    assert args.init is None
    assert args.timeout == 120.0


def test_parser_init_and_timeout():
    args = build_parser().parse_args(
        ["--init", "0", "0", "0", "--goal", "1", "0", "1.57", "--timeout", "30"])
    assert args.init == [0.0, 0.0, 0.0]
    assert args.timeout == 30.0


def test_yaw_to_quat_reused():
    from chassis_bringup.send_goal import yaw_to_quat
    qz, qw = yaw_to_quat(0.0)
    assert qz == pytest.approx(0.0)
    assert qw == pytest.approx(1.0)
