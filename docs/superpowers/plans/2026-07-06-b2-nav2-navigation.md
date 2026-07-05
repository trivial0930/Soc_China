# B2 Nav2 Autonomous Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One-command Nav2 bring-up on the saved `lab_map` so a CLI-sent goal drives the RDK X5 mecanum chassis autonomously to the target (xy≤10cm), avoiding obstacles.

**Architecture:** A new `nav.launch.py` mirrors the existing `mapping.launch.py`: it starts the chassis base (lidar `/scan` + IMU-fused EKF `odom→base_link` + `stm32_bridge` + static TF) and includes the stock `nav2_bringup` `localization_launch.py` (map_server + AMCL) and `navigation_launch.py` (planner/controller/bt_navigator/behaviors/velocity_smoother/lifecycle), all fed our `nav2_params.yaml` + `~/maps/lab_map.yaml`, with the smoother's output remapped to `/cmd_vel` (what `stm32_bridge` subscribes). A `send_goal.py` (nav2_simple_commander) sets the AMCL initial pose and drives one goal, run from the RDK over SSH. Nav is an independent mode: teleop_safety does NOT run; Nav2 owns `/cmd_vel`.

**Tech Stack:** ROS 2 Humble, `nav2_bringup`, `nav2_simple_commander`, MPPI controller (Omni), AMCL (OmniMotionModel), Python launch, pytest (host, ROS-free helpers).

## Global Constraints

- Package: everything lives in `rdk_x5/ros2_ws/src/chassis_bringup` (follow its existing patterns: `data_files` installs `launch/*.launch.py` + `config/*.yaml`; console scripts via `entry_points`).
- Reuse, don't duplicate: import `yaw_to_quat` from the existing `chassis_bringup.waypoint_patrol` (stdlib-only top level; ROS imported lazily inside functions, so it imports fine on a host without ROS).
- Frames: `map ─[amcl]→ odom ─[EKF]→ base_link ─[static]→ laser`. Do NOT run slam_toolbox (that is B1/mapping).
- cmd_vel: Nav2 `velocity_smoother` output remaps to `/cmd_vel`; do NOT modify `stm32_bridge`; do NOT launch `teleop_safety` in nav mode.
- Map on RDK: `~/maps/lab_map.yaml` (repo backup: `rdk_x5/maps/lab_map.{pgm,yaml}`).
- Resource: before launching nav on the RDK, `systemctl stop voice-asr.service` to free CPU (Nav2 MPPI + AMCL + dual costmap is heavy).
- Test-writer note: `main()` bodies that need ROS/Nav2 are NOT host-unit-tested; only pure helpers are. ROS glue is verified on-board in Task 5.
- Commit messages end with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

---

## File Structure

- Create `rdk_x5/ros2_ws/src/chassis_bringup/chassis_bringup/send_goal.py` — single-goal Nav2 client (pure helpers + `main()`).
- Create `rdk_x5/ros2_ws/src/chassis_bringup/tests/test_send_goal.py` — host unit tests for the pure helpers.
- Modify `rdk_x5/ros2_ws/src/chassis_bringup/setup.py` — add `send_goal` console script entry point.
- Create `rdk_x5/ros2_ws/src/chassis_bringup/launch/nav.launch.py` — one-command nav bring-up.
- Create `docs/ops/lab_nav_procedure.md` — operator manual.

---

## Task 1: `send_goal.py` pure helpers + unit tests

**Files:**
- Create: `rdk_x5/ros2_ws/src/chassis_bringup/chassis_bringup/send_goal.py` (helpers only this task)
- Test: `rdk_x5/ros2_ws/src/chassis_bringup/tests/test_send_goal.py`

**Interfaces:**
- Consumes: `chassis_bringup.waypoint_patrol.yaw_to_quat(yaw:float)->(qz:float,qw:float)`.
- Produces: `parse_pose(values: Optional[list[float]]) -> Optional[tuple[float,float,float]]` (None→None; len!=3→ValueError); `build_parser() -> argparse.ArgumentParser` (`--init X Y YAW` optional, `--goal X Y YAW` required, `--timeout` float default 120.0).

- [ ] **Step 1: Write the failing tests**

Create `rdk_x5/ros2_ws/src/chassis_bringup/tests/test_send_goal.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd rdk_x5/ros2_ws/src/chassis_bringup && python3 -m pytest tests/test_send_goal.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'chassis_bringup.send_goal'`
(If pytest missing on host, use a venv: `python3 -m venv /tmp/nv && /tmp/nv/bin/pip -q install pytest && PYTHONPATH=. /tmp/nv/bin/python -m pytest tests/test_send_goal.py -q`.)

- [ ] **Step 3: Write the helpers**

Create `rdk_x5/ros2_ws/src/chassis_bringup/chassis_bringup/send_goal.py`:

```python
#!/usr/bin/env python3
"""Send one Nav2 goal (with optional AMCL initial pose) via nav2_simple_commander.

Drives a single goToPose and prints feedback until arrival/failure/timeout. Pure
helpers (arg parsing) are unit-tested in tests/test_send_goal.py without ROS.

Run on the RDK once the Nav2 stack is up (nav.launch.py):
  ros2 run chassis_bringup send_goal --init 0 0 0 --goal 1.5 0 0
  ros2 run chassis_bringup send_goal --goal 1.5 0 0     # skip initialpose (already localized)
"""
from __future__ import annotations

import argparse
from typing import List, Optional, Tuple

# Reuse the planar yaw->quaternion helper (DRY; imports ROS-free).
from chassis_bringup.waypoint_patrol import yaw_to_quat  # noqa: F401

Pose = Tuple[float, float, float]


def parse_pose(values: Optional[List[float]]) -> Optional[Pose]:
    """[x, y, yaw] -> (x, y, yaw); None -> None. Raises ValueError on bad length."""
    if values is None:
        return None
    if len(values) != 3:
        raise ValueError("pose must be exactly 3 numbers: x y yaw")
    return (float(values[0]), float(values[1]), float(values[2]))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Send one Nav2 goal")
    p.add_argument("--init", nargs=3, type=float, metavar=("X", "Y", "YAW"),
                   default=None, help="AMCL initial pose; omit if already localized")
    p.add_argument("--goal", nargs=3, type=float, metavar=("X", "Y", "YAW"),
                   required=True, help="goal pose in the map frame")
    p.add_argument("--timeout", type=float, default=120.0,
                   help="cancel if not arrived within this many seconds")
    return p
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd rdk_x5/ros2_ws/src/chassis_bringup && python3 -m pytest tests/test_send_goal.py -q` (or the venv form from Step 2)
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add rdk_x5/ros2_ws/src/chassis_bringup/chassis_bringup/send_goal.py \
        rdk_x5/ros2_ws/src/chassis_bringup/tests/test_send_goal.py
git commit -m "feat(chassis_bringup): send_goal.py pure helpers + host tests

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `send_goal.py` main() + console script entry point

**Files:**
- Modify: `rdk_x5/ros2_ws/src/chassis_bringup/chassis_bringup/send_goal.py` (append `main()`)
- Modify: `rdk_x5/ros2_ws/src/chassis_bringup/setup.py` (add entry point)

**Interfaces:**
- Consumes: `parse_pose`, `build_parser`, `yaw_to_quat` from Task 1; `nav2_simple_commander.robot_navigator.BasicNavigator`/`TaskResult`.
- Produces: console script `send_goal = chassis_bringup.send_goal:main`; `main()` exits 0 on `TaskResult.SUCCEEDED`, else 1.

- [ ] **Step 1: Append `main()` to `send_goal.py`**

Add at the end of `rdk_x5/ros2_ws/src/chassis_bringup/chassis_bringup/send_goal.py`:

```python
def _make_pose(nav, x: float, y: float, yaw: float):
    """PoseStamped in the map frame (ROS types resolved lazily)."""
    from geometry_msgs.msg import PoseStamped
    ps = PoseStamped()
    ps.header.frame_id = "map"
    ps.header.stamp = nav.get_clock().now().to_msg()
    ps.pose.position.x = x
    ps.pose.position.y = y
    qz, qw = yaw_to_quat(yaw)
    ps.pose.orientation.z = qz
    ps.pose.orientation.w = qw
    return ps


def main() -> None:
    import time
    import rclpy
    from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult

    args = build_parser().parse_args()
    init = parse_pose(args.init)
    goal = parse_pose(args.goal)

    rclpy.init()
    nav = BasicNavigator()

    if init is not None:
        nav.setInitialPose(_make_pose(nav, *init))
        nav.get_logger().info(f"initial pose set to {init}")

    nav.get_logger().info("waiting for Nav2 to become active...")
    nav.waitUntilNav2Active()

    nav.goToPose(_make_pose(nav, *goal))
    nav.get_logger().info(f"navigating to {goal} (timeout {args.timeout}s)...")

    t0 = time.time()
    while not nav.isTaskComplete():
        fb = nav.getFeedback()
        if fb is not None:
            nav.get_logger().info(f"remaining {fb.distance_remaining:.2f} m")
        if time.time() - t0 > args.timeout:
            nav.cancelTask()
            nav.get_logger().warn("timeout -> cancelled")
            break
        time.sleep(1.0)

    result = nav.getResult()
    name = getattr(result, "name", str(result))
    nav.get_logger().info(f"result: {name}")
    rclpy.shutdown()
    raise SystemExit(0 if result == TaskResult.SUCCEEDED else 1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Add the entry point in `setup.py`**

In `rdk_x5/ros2_ws/src/chassis_bringup/setup.py`, change the `console_scripts` list from:

```python
        "console_scripts": [
            "waypoint_patrol = chassis_bringup.waypoint_patrol:main",
        ],
```

to:

```python
        "console_scripts": [
            "waypoint_patrol = chassis_bringup.waypoint_patrol:main",
            "send_goal = chassis_bringup.send_goal:main",
        ],
```

- [ ] **Step 3: Re-run host tests (main() must not break the import)**

Run: `cd rdk_x5/ros2_ws/src/chassis_bringup && python3 -m pytest tests/test_send_goal.py -q` (or venv form)
Expected: PASS (8 passed) — importing the module must still work with only stdlib at top level (ROS imports live inside `main`/`_make_pose`).

- [ ] **Step 4: Commit**

```bash
git add rdk_x5/ros2_ws/src/chassis_bringup/chassis_bringup/send_goal.py \
        rdk_x5/ros2_ws/src/chassis_bringup/setup.py
git commit -m "feat(chassis_bringup): send_goal main() + console entry point

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `nav.launch.py` one-command nav bring-up

**Files:**
- Create: `rdk_x5/ros2_ws/src/chassis_bringup/launch/nav.launch.py`

**Interfaces:**
- Consumes: existing `chassis_bringup/launch/bringup.launch.py` (arg `use_imu`), `lslidar_driver` node, `nav2_bringup` share launches `localization_launch.py` + `navigation_launch.py`, `nav2_params.yaml`.
- Produces: `ros2 launch chassis_bringup nav.launch.py [map:=... params_file:=... use_imu:=true]` bringing up base + AMCL + Nav2 with smoother→`/cmd_vel`.

- [ ] **Step 1: Write `nav.launch.py`**

Create `rdk_x5/ros2_ws/src/chassis_bringup/launch/nav.launch.py`:

```python
"""一键自主导航(B2):雷达 + 里程计/IMU-EKF/TF + AMCL 定位(静态 lab_map)+ Nav2 栈。

导航为独立模式:teleop_safety 不跑,Nav2 直接控 /cmd_vel。起之前先腾 CPU:
    systemctl stop voice-asr.service

启动:
    ros2 launch chassis_bringup nav.launch.py
    ros2 launch chassis_bringup nav.launch.py map:=/root/maps/lab_map.yaml

TF 链:map -(amcl)-> odom -(EKF)-> base_link -(static)-> laser。
发目标(另开一个终端):
    ros2 run chassis_bringup send_goal --init 0 0 0 --goal 1.5 0 0
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    bringup_share = FindPackageShare("chassis_bringup")
    nav2_share = FindPackageShare("nav2_bringup")

    use_imu = LaunchConfiguration("use_imu")
    lslidar_params = LaunchConfiguration("lslidar_params")
    params_file = LaunchConfiguration("params_file")
    map_yaml = LaunchConfiguration("map")

    bringup = PathJoinSubstitution([bringup_share, "launch", "bringup.launch.py"])
    localization = PathJoinSubstitution(
        [nav2_share, "launch", "localization_launch.py"])
    navigation = PathJoinSubstitution(
        [nav2_share, "launch", "navigation_launch.py"])
    default_params = PathJoinSubstitution(
        [bringup_share, "config", "nav2_params.yaml"])

    return LaunchDescription([
        DeclareLaunchArgument("use_imu", default_value="true",
                              description="fuse BMI088 /imu in EKF"),
        DeclareLaunchArgument(
            "lslidar_params",
            default_value="/root/Soc_China/rdk_x5/ros2_ws/src/lslidar_driver/params/lsx10.yaml"),
        DeclareLaunchArgument("params_file", default_value=default_params),
        DeclareLaunchArgument("map", default_value="/root/maps/lab_map.yaml"),

        # 1) N10 lidar -> /scan
        Node(package="lslidar_driver", executable="lslidar_driver_node",
             name="lslidar_driver_node", output="screen",
             parameters=[lslidar_params]),

        # 2) wheel odom + IMU-fused EKF (odom->base_link) + static TF (base_link->laser)
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource([bringup]),
            launch_arguments={"use_imu": use_imu}.items()),

        # 3) AMCL localization on the saved map (map->odom, map_server serves lab_map)
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource([localization]),
            launch_arguments={"map": map_yaml, "params_file": params_file,
                              "use_sim_time": "false"}.items()),

        # 4) Nav2 core (planner/controller/bt/behaviors/smoother/lifecycle).
        #    Remap the smoother's output to /cmd_vel (what stm32_bridge subscribes).
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource([navigation]),
            launch_arguments={"params_file": params_file,
                              "use_sim_time": "false"}.items()),
    ])
```

- [ ] **Step 2: Verify the launch file parses (host, no nodes started)**

Run: `cd rdk_x5/ros2_ws/src/chassis_bringup && python3 -c "import ast; ast.parse(open('launch/nav.launch.py').read()); print('OK')"`
Expected: `OK` (full launch validation happens on-board in Task 5, which needs ROS + nav2_bringup).

- [ ] **Step 3: Commit**

```bash
git add rdk_x5/ros2_ws/src/chassis_bringup/launch/nav.launch.py
git commit -m "feat(chassis_bringup): nav.launch.py one-command Nav2 bring-up

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

**Note on the smoother→/cmd_vel remap:** `navigation_launch.py` in nav2_bringup Humble applies its remappings to all nav2 nodes; `velocity_smoother` publishes `cmd_vel` by default and `controller_server` publishes `cmd_vel` too, both under the default which resolves to `/cmd_vel` at the root namespace — this already matches `stm32_bridge`'s subscription. Confirm in Task 5 that `/cmd_vel` has exactly one active publisher while navigating (the smoother). If nav2_bringup instead routes to `/cmd_vel_smoothed`, add `-r /cmd_vel_smoothed:=/cmd_vel` by passing a remap — handled as a fix in Task 5 if observed.

---

## Task 4: Operator manual `docs/ops/lab_nav_procedure.md`

**Files:**
- Create: `docs/ops/lab_nav_procedure.md`

- [ ] **Step 1: Write the manual**

Create `docs/ops/lab_nav_procedure.md`:

```markdown
# 实验室自主导航(B2 / Nav2)操作手册

前提:B1 已建好并存了 `~/maps/lab_map.{pgm,yaml}`;里程/固件已标定;IMU 正常。

## 1. 腾 CPU(必做)
Nav2(MPPI + AMCL + 双 costmap)吃 CPU 比 slam 还重:
```
systemctl stop voice-asr.service
```

## 2. 放车到已知起点
把车放在地图上一个**记得住的起点**(建图起点附近最稳),记下它在地图坐标里的大致 (x, y, yaw)。

## 3. 一键起导航栈
```
ros2 launch chassis_bringup nav.launch.py
```
起底盘基座 + AMCL(载入 lab_map)+ Nav2。

## 4. 验栈(另一个终端)
```
ros2 node list | grep -E "amcl|controller_server|planner_server|bt_navigator|map_server"
ros2 lifecycle get /amcl /controller_server /planner_server /bt_navigator   # 应 active
ros2 run tf2_ros tf2_echo map odom      # 非空 = map->odom 有了
ros2 topic echo --once /amcl_pose       # 有位姿
```

## 5. 定位收敛
```
ros2 run chassis_bringup send_goal --init <x> <y> <yaw> --goal <x> <y> <yaw>
```
`--init` 播初始位姿。若粒子云不收敛,原地缓慢转一圈或前后挪一点让 AMCL 咬住扫描。

## 6. 发目标 + 观察
先发**近目标(~1–2m)**:
```
ros2 run chassis_bringup send_goal --goal <x> <y> <yaw>
```
脚本打印剩余距离,到达/失败/超时都会报;车到达容差 xy≤10cm、yaw≤0.15。

## 7. 动态避障测试
导航中在路上放个障碍 → local costmap 标记 → Nav2 重规划绕过(或安全停)。

## 坑
- 起 nav 前没停 voice-asr → controller/AMCL 跟不上,路径抖/丢定位。
- 车放地上留足空地;先发短目标;失控就 Ctrl-C 掉 nav.launch(会停发 /cmd_vel,bridge 500ms cmd 超时自动停车)。
- 黑药丸驱动电机时仍有挂死风险(功率地未根治);跑动中 /odom 断 → 复位 STM32(见 [[runaway-fix-and-blackpill-hang]])。
- `robot_radius/inflation/速度上限` 为模板值,首次按实车观察微调 nav2_params.yaml。
```

- [ ] **Step 2: Commit**

```bash
git add docs/ops/lab_nav_procedure.md
git commit -m "docs(ops): B2 lab autonomous navigation procedure

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: On-board bring-up + verification (RDK, over SSH)

**Files:** none (integration/verification). Any fixes found (e.g. cmd_vel remap, robot_radius) are committed here.

**Interfaces:**
- Consumes: everything above, deployed to the RDK. RDK reachable at `root@192.168.128.10` (USB link) or `root@100.108.218.113` (Tailscale). Map at `/root/maps/lab_map.yaml`.

- [ ] **Step 1: Deploy source to the RDK**

Copy the new/changed files to the RDK checkout and colcon build the package:
```bash
# from Mac: rsync the package sources (adjust host as needed)
rsync -az rdk_x5/ros2_ws/src/chassis_bringup/ root@192.168.128.10:/root/Soc_China/rdk_x5/ros2_ws/src/chassis_bringup/
ssh root@192.168.128.10 'export HOME=/root; source /opt/ros/humble/setup.bash; \
  cd /root/Soc_China/rdk_x5/ros2_ws && colcon build --packages-select chassis_bringup 2>&1 | tail -5'
```
Expected: build finishes, `send_goal` + `nav.launch.py` installed. Confirm the map exists: `ssh root@192.168.128.10 'ls -la /root/maps/lab_map.yaml'` (if absent, `scp rdk_x5/maps/lab_map.* root@192.168.128.10:/root/maps/`).

- [ ] **Step 2: Free CPU + launch nav (transient systemd, survives SSH drop)**

```bash
ssh root@192.168.128.10 'systemctl stop voice-asr.service 2>/dev/null; \
  systemctl reset-failed navstack-tmp 2>/dev/null; \
  systemd-run --unit=navstack-tmp --collect bash -c \
    "export HOME=/root; source /opt/ros/humble/setup.bash; \
     source /root/Soc_China/rdk_x5/ros2_ws/install/setup.bash; \
     exec ros2 launch chassis_bringup nav.launch.py"'
sleep 20
```
(If the stm32 bridge is not already up from another unit, it is included via `bringup.launch.py`; confirm one `/cmd_vel` consumer in Step 4.)

- [ ] **Step 3: Verify the stack is active**

```bash
ssh root@192.168.128.10 'export HOME=/root; source /opt/ros/humble/setup.bash; \
  source /root/Soc_China/rdk_x5/ros2_ws/install/setup.bash; \
  echo "== nodes =="; ros2 node list | grep -E "amcl|controller_server|planner_server|bt_navigator|map_server|lslidar|ekf"; \
  echo "== lifecycle =="; for n in /amcl /controller_server /planner_server /bt_navigator /map_server; do echo -n "$n: "; ros2 lifecycle get $n; done; \
  echo "== tf map->odom =="; timeout 5 ros2 run tf2_ros tf2_echo map odom 2>/dev/null | grep -m1 Translation || echo "NO map->odom"; \
  echo "== /scan hz =="; timeout 3 ros2 topic hz /scan 2>/dev/null | grep -i average'
```
Expected: nav2 nodes present; each lifecycle `active`; `map->odom` Translation printed; `/scan` ~10Hz. If a node is `unconfigured/inactive`, check the lifecycle_manager autostart in nav2_params/launch and re-launch.

- [ ] **Step 4: Confirm exactly one /cmd_vel publisher (the smoother)**

```bash
ssh root@192.168.128.10 'export HOME=/root; source /opt/ros/humble/setup.bash; \
  source /root/Soc_China/rdk_x5/ros2_ws/install/setup.bash; ros2 topic info /cmd_vel'
```
Expected: `Publisher count: 1` (velocity_smoother), `Subscription count: 1` (stm32_bridge). If Publisher is 0, the smoother publishes elsewhere → add `-r cmd_vel_smoothed:=/cmd_vel` remap to the `navigation` include in `nav.launch.py`, rebuild, re-launch, and commit the fix.

- [ ] **Step 5: Localize (initial pose + convergence)**

Place the robot at the known start on the map; then:
```bash
ssh root@192.168.128.10 'export HOME=/root; source /opt/ros/humble/setup.bash; \
  source /root/Soc_China/rdk_x5/ros2_ws/install/setup.bash; \
  ros2 topic pub --once /initialpose geometry_msgs/msg/PoseWithCovarianceStamped \
    "{header: {frame_id: map}, pose: {pose: {position: {x: <x>, y: <y>}, orientation: {z: 0.0, w: 1.0}}}}"; \
  timeout 4 ros2 topic echo --once /amcl_pose 2>/dev/null | grep -A3 position'
```
Nudge the robot a little (a short teleop-free push or a tiny goal) if the AMCL cloud is spread; confirm `/amcl_pose` settles near the real pose.

- [ ] **Step 6: First autonomous goal (SHORT, ~1m, floor clear)**

```bash
ssh root@192.168.128.10 'export HOME=/root; source /opt/ros/humble/setup.bash; \
  source /root/Soc_China/rdk_x5/ros2_ws/install/setup.bash; \
  ros2 run chassis_bringup send_goal --init <x> <y> <yaw> --goal <x+1> <y> <yaw> --timeout 60'
```
Expected: prints decreasing `remaining ... m`, robot drives there, ends `result: SUCCEEDED`. Then measure final pose vs goal (should be within xy≤10cm). If it oscillates/overshoots, note MPPI/costmap tuning for a follow-up (do not block bring-up).

- [ ] **Step 7: Dynamic obstacle avoidance**

Send a goal ~2m ahead; while it drives, place a box in the straight-line path.
Expected: local costmap marks it, the planned path bends around it, robot reaches the goal (or stops safely if fully blocked). Capture evidence: `ros2 topic echo --once /plan` before vs after placing the obstacle shows a different path, or observe the robot visibly detour.

- [ ] **Step 8: Record results + commit any on-board fixes**

Write a short validation note `docs/validation/daily/2026-07-06-b2-nav2-bringup.md` (stack active, localization converged, goal reached within Xcm, avoidance observed; list any params tweaked). Commit it plus any nav2_params/nav.launch fixes made during Steps 4/6:
```bash
git add docs/validation/daily/2026-07-06-b2-nav2-bringup.md rdk_x5/ros2_ws/src/chassis_bringup/
git commit -m "test(b2): on-board Nav2 bring-up — localize, goal reached, avoidance verified

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 9: Tear down (restore normal mode)**

```bash
ssh root@192.168.128.10 'systemctl stop navstack-tmp 2>/dev/null; \
  systemctl start voice-asr.service 2>/dev/null'
```

---

## Self-Review

**Spec coverage:**
- AMCL localization on lab_map → Task 3 (localization include) + Task 5 Step 5. ✓
- nav.launch.py one-command (base + nav2) → Task 3. ✓
- velocity_smoother→/cmd_vel, no bridge change, teleop off → Task 3 (+ Step 4 verify/fix). ✓
- send_goal.py (setInitialPose + goToPose + monitor) → Tasks 1–2. ✓
- lab_nav_procedure.md → Task 4. ✓
- Success criteria (lifecycle active, tf map→odom, amcl converge, goal xy≤10cm, avoidance) → Task 5 Steps 3,5,6,7. ✓
- Resource: stop voice-asr → Global Constraints + Task 5 Step 2 + manual. ✓
- YAGNI (no App/rendering/formal mode) → not in any task. ✓

**Placeholder scan:** `<x>/<y>/<yaw>` in Task 5 and the manual are operator-supplied runtime values (the robot's real start/goal on the map), not plan placeholders — they cannot be known until the robot is physically placed. All code steps contain complete code.

**Type consistency:** `parse_pose` / `build_parser` / `yaw_to_quat` / `_make_pose` signatures match across Tasks 1–2; `send_goal` entry point matches the module path; `nav.launch.py` arg names (`map`, `params_file`, `use_imu`, `lslidar_params`) consistent.
