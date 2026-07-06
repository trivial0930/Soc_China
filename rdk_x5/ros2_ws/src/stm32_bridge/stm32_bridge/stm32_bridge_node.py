#!/usr/bin/env python3
"""RDK X5 <-> STM32 chassis bridge (ROS 2).

Subscribes /cmd_vel (geometry_msgs/Twist), sends the RDK-STM32 UART protocol
(SET_MODE / HEARTBEAT / CMD_VEL) over the 40-pin UART (/dev/ttyS1, USART2 on the
STM32 side after the 2026-06-08 pin migration). Reads STM32 STATUS / ODOM frames,
integrates wheel-encoder odometry and publishes nav_msgs/Odometry (+ TF
odom->base_link). On shutdown / cmd timeout the STM32 stops the chassis itself.

Reuses the shared protocol codec at shared/protocol/rdk_stm32_uart.py and the
pure odometry math in stm32_bridge/mecanum_odometry.py (both unit-tested host-side).
"""

from __future__ import annotations

import math
import sys
import time
from pathlib import Path

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist, TransformStamped
from nav_msgs.msg import Odometry
from sensor_msgs.msg import JointState
from std_msgs.msg import String
import math as _math


def _find_repo_root(start: Path) -> Path:
    """Walk up until we find shared/protocol/rdk_stm32_uart.py."""
    for parent in [start, *start.parents]:
        if (parent / "shared" / "protocol" / "rdk_stm32_uart.py").exists():
            return parent
    # Fallback: typical layout repo/rdk_x5/ros2_ws/src/stm32_bridge/stm32_bridge/<file>
    return start.parents[5]


_REPO_ROOT = _find_repo_root(Path(__file__).resolve())
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from shared.protocol.rdk_stm32_uart import (  # noqa: E402
    FrameParser,
    FrameType,
    Mode,
    StopReason,
    clamp_cmd_vel,
    encode_frame,
    next_seq,
    pack_cmd_vel,
    pack_heartbeat,
    pack_set_mode,
    pack_stop,
    unpack_ack,
    unpack_fault,
    unpack_odom,
    unpack_status,
)

# Local package import (works both installed and from source tree).
try:
    from stm32_bridge.mecanum_odometry import (
        MecanumOdometry, MecanumOdometryConfig, wrapped_delta_u16,
    )
except ImportError:  # pragma: no cover - source-tree fallback
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from stm32_bridge.mecanum_odometry import (
        MecanumOdometry, MecanumOdometryConfig, wrapped_delta_u16,
    )

MODE_BY_NAME = {
    "idle": Mode.IDLE,
    "manual": Mode.MANUAL,
    "auto": Mode.AUTO,
    "test": Mode.TEST,
}


class Stm32BridgeNode(Node):
    def __init__(self) -> None:
        super().__init__("stm32_bridge")

        # ---- parameters ----
        self.declare_parameter("port", "/dev/ttyS1")
        self.declare_parameter("baud", 115200)
        self.declare_parameter("mode", "manual")
        self.declare_parameter("cmd_vel_topic", "/cmd_vel")
        self.declare_parameter("heartbeat_hz", 5.0)
        self.declare_parameter("cmd_rate_hz", 20.0)
        self.declare_parameter("serial_poll_hz", 200.0)
        self.declare_parameter("cmd_vel_timeout_s", 0.5)
        # geometry (match firmware app_chassis_init)
        self.declare_parameter("wheel_radius_m", 0.05)
        self.declare_parameter("half_length_m", 0.12)
        self.declare_parameter("half_width_m", 0.10)
        self.declare_parameter("ticks_per_rev", 1320.0)  # PLACEHOLDER - calibrate
        self.declare_parameter("encoder_sign", [1, 1, 1, 1])  # LF,RF,LR,RR
        # velocity clamp (protocol int16 mm/s, mrad/s)
        self.declare_parameter("max_vx_mm_s", 400)
        self.declare_parameter("max_vy_mm_s", 400)
        self.declare_parameter("max_wz_mrad_s", 1500)
        # frames / tf
        self.declare_parameter("publish_tf", True)
        self.declare_parameter("odom_frame_id", "odom")
        self.declare_parameter("base_frame_id", "base_link")
        self.declare_parameter("publish_joint_states", True)
        self.declare_parameter("wheel_joint_names",
                               ["lf_wheel_joint", "rf_wheel_joint",
                                "lr_wheel_joint", "rr_wheel_joint"])

        gp = self.get_parameter
        self.port = gp("port").value
        self.baud = int(gp("baud").value)
        self.mode = MODE_BY_NAME.get(str(gp("mode").value).lower(), Mode.MANUAL)
        self.cmd_vel_timeout_s = float(gp("cmd_vel_timeout_s").value)
        self.max_vx = int(gp("max_vx_mm_s").value)
        self.max_vy = int(gp("max_vy_mm_s").value)
        self.max_wz = int(gp("max_wz_mrad_s").value)
        self.publish_tf = bool(gp("publish_tf").value)
        self.odom_frame = str(gp("odom_frame_id").value)
        self.base_frame = str(gp("base_frame_id").value)
        self.publish_joint_states = bool(gp("publish_joint_states").value)
        self.wheel_joint_names = list(gp("wheel_joint_names").value)
        self._wheel_ticks_per_rev = float(gp("ticks_per_rev").value)

        signs = list(gp("encoder_sign").value)
        self.odom = MecanumOdometry(config=MecanumOdometryConfig(
            wheel_radius_m=float(gp("wheel_radius_m").value),
            half_length_m=float(gp("half_length_m").value),
            half_width_m=float(gp("half_width_m").value),
            ticks_per_rev=float(gp("ticks_per_rev").value),
            encoder_sign=(signs + [1, 1, 1, 1])[:4],
        ))

        # ---- state ----
        self._seq = 0
        self._target = (0, 0, 0)          # vx_mm_s, vy_mm_s, wz_mrad_s
        self._last_cmd_vel_ts = 0.0
        self._last_hb_ts = 0.0
        self._hb_period = 1.0 / max(0.1, float(gp("heartbeat_hz").value))
        self._parser = FrameParser()
        self._last_odom_t = None
        self._ser = None
        # auto-reconnect: the STM32 re-enumerates on a watchdog reset (motor-noise
        # hang). Rate-limit reopen attempts so we don't spam serial.Serial() while
        # the by-id symlink is still gone mid-enumeration.
        self._reconnect_period_s = 1.0
        self._next_open_ts = 0.0
        self._serial_alive = False
        # cumulative per-wheel angle (rad) for /joint_states, order LF,RF,LR,RR
        self._joint_angle = [0.0, 0.0, 0.0, 0.0]
        self._joint_last_ticks = None

        # ---- ROS I/O ----
        self.odom_pub = self.create_publisher(Odometry, "odom", 10)
        self.status_pub = self.create_publisher(String, "stm32/status", 10)
        self.joint_pub = (self.create_publisher(JointState, "joint_states", 10)
                          if self.publish_joint_states else None)
        self.create_subscription(Twist, str(gp("cmd_vel_topic").value), self._on_cmd_vel, 10)

        self._tf_broadcaster = None
        if self.publish_tf:
            try:
                from tf2_ros import TransformBroadcaster
                self._tf_broadcaster = TransformBroadcaster(self)
            except Exception as exc:  # pragma: no cover
                self.get_logger().warn(f"tf2_ros unavailable, TF disabled: {exc}")

        self._open_serial()

        self.create_timer(1.0 / float(gp("cmd_rate_hz").value), self._on_cmd_timer)
        self.create_timer(1.0 / float(gp("serial_poll_hz").value), self._on_serial_poll)
        self.get_logger().info(
            f"stm32_bridge up: port={self.port}@{self.baud} mode={self.mode.name} "
            f"ticks_per_rev={self.odom.config.ticks_per_rev} (calibrate me)"
        )

    # ---------------- serial ----------------
    def _open_serial(self) -> None:
        """Initial open at startup (kept for construction path)."""
        self._ensure_serial(force=True)

    def _drop_serial(self, why: str) -> None:
        """Tear down a dead fd (STM32 re-enumerated) so the timers reconnect."""
        if self._ser is not None or self._serial_alive:
            self.get_logger().warn(f"serial link lost ({why}); will reconnect")
        try:
            if self._ser is not None:
                self._ser.close()
        except Exception:
            pass
        self._ser = None
        self._serial_alive = False

    def _ensure_serial(self, force: bool = False) -> bool:
        """Open the port if not already open, rate-limited. Re-inits STM32 state
        on a fresh open (re-send SET_MODE, resync odom baseline, drop partial
        frames) so a watchdog reset doesn't leave us on a stale fd or jump odom."""
        if self._ser is not None:
            return True
        now = time.monotonic()
        if not force and now < self._next_open_ts:
            return False
        self._next_open_ts = now + self._reconnect_period_s
        try:
            import serial
        except ImportError:
            self.get_logger().error("pyserial not installed; bridge will not talk to STM32")
            return False
        try:
            self._ser = serial.Serial(self.port, self.baud, timeout=0)
        except Exception as exc:
            # by-id symlink may be gone mid re-enumeration; quiet retry.
            self._ser = None
            return False
        # fresh link: re-init STM32 + resync so odom stays continuous across reset
        self._parser = FrameParser()
        self._last_odom_t = None
        self._joint_last_ticks = None
        try:
            self.odom.resync()
        except Exception:
            pass
        self._serial_alive = True
        self._send(FrameType.SET_MODE, pack_set_mode(self.mode))
        self.get_logger().info(f"opened {self.port}, sent SET_MODE {self.mode.name}")
        return True

    def _send(self, ftype: FrameType, payload: bytes) -> None:
        if self._ser is None:
            return
        raw = encode_frame(ftype, self._seq, payload)
        self._seq = next_seq(self._seq)
        try:
            self._ser.write(raw)
        except Exception as exc:  # STM32 re-enumerated -> drop + reconnect
            self._drop_serial(f"write failed: {exc}")

    # ---------------- subscribers ----------------
    def _on_cmd_vel(self, msg: Twist) -> None:
        vx, vy, wz, clamped = clamp_cmd_vel(
            int(round(msg.linear.x * 1000.0)),
            int(round(msg.linear.y * 1000.0)),
            int(round(msg.angular.z * 1000.0)),
        )
        # extra project-level clamp
        vx = max(-self.max_vx, min(self.max_vx, vx))
        vy = max(-self.max_vy, min(self.max_vy, vy))
        wz = max(-self.max_wz, min(self.max_wz, wz))
        self._target = (vx, vy, wz)
        self._last_cmd_vel_ts = time.monotonic()
        if clamped:
            self.get_logger().warn("cmd_vel clamped to protocol range")

    # ---------------- timers ----------------
    def _on_cmd_timer(self) -> None:
        # reconnect if the STM32 re-enumerated (watchdog reset). Rate-limited.
        if self._ser is None:
            self._ensure_serial()
            return
        now = time.monotonic()
        if now - self._last_hb_ts >= self._hb_period:
            self._send(FrameType.HEARTBEAT, pack_heartbeat(int(now * 1000) & 0xFFFFFFFF))
            self._last_hb_ts = now
        # stop sending stale velocities; STM32 also has its own cmd timeout
        if now - self._last_cmd_vel_ts > self.cmd_vel_timeout_s:
            self._target = (0, 0, 0)
        vx, vy, wz = self._target
        self._send(FrameType.CMD_VEL, pack_cmd_vel(vx, vy, wz))

    def _on_serial_poll(self) -> None:
        if self._ser is None:
            return
        try:
            data = self._ser.read(256)
        except Exception as exc:  # STM32 re-enumerated -> drop + reconnect
            self._drop_serial(f"read failed: {exc}")
            return
        if not data:
            return
        for frame in self._parser.feed(data):
            self._handle_frame(frame)

    # ---------------- frame handling ----------------
    def _handle_frame(self, frame) -> None:
        if frame.frame_type == FrameType.ODOM:
            self._handle_odom(frame.payload)
        elif frame.frame_type == FrameType.STATUS:
            st = unpack_status(frame.payload)
            self.status_pub.publish(String(data=(
                f"mode={st.mode.name} estop={int(st.estop)} fault=0x{st.fault_code:04X} "
                f"battery={st.battery_mv}mV comm={st.comm_state.name}"
            )))
        elif frame.frame_type == FrameType.FAULT:
            code, detail = unpack_fault(frame.payload)
            self.get_logger().warn(f"STM32 FAULT 0x{code:04X} detail=0x{detail:04X}")
        elif frame.frame_type == FrameType.ACK:
            ack = unpack_ack(frame.payload)
            if ack.result.name not in ("OK", "CLAMPED"):
                self.get_logger().warn(f"NACK {ack.result.name} for type=0x{int(ack.ack_type):02X}")

    def _handle_odom(self, payload: bytes) -> None:
        ticks = list(unpack_odom(payload))  # LF, RF, LR, RR (raw 16-bit)
        now = time.monotonic()
        dt = 0.0 if self._last_odom_t is None else (now - self._last_odom_t)
        self._last_odom_t = now
        st = self.odom.update(ticks[0], ticks[1], ticks[2], ticks[3], dt)
        self._publish_odom(st)
        if self.joint_pub is not None:
            self._publish_joints(ticks, dt)

    def _publish_joints(self, ticks, dt: float) -> None:
        signs = self.odom.config.encoder_sign
        rad_per_tick = 2.0 * _math.pi / self._wheel_ticks_per_rev
        vels = [0.0, 0.0, 0.0, 0.0]
        if self._joint_last_ticks is not None and dt > 0.0:
            for i in range(4):
                d = signs[i] * wrapped_delta_u16(ticks[i], self._joint_last_ticks[i])
                self._joint_angle[i] += d * rad_per_tick
                vels[i] = d * rad_per_tick / dt
        self._joint_last_ticks = ticks

        msg = JointState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.name = list(self.wheel_joint_names)
        msg.position = list(self._joint_angle)
        msg.velocity = vels
        self.joint_pub.publish(msg)

    def _publish_odom(self, st) -> None:
        stamp = self.get_clock().now().to_msg()
        qz = math.sin(st.theta / 2.0)
        qw = math.cos(st.theta / 2.0)

        msg = Odometry()
        msg.header.stamp = stamp
        msg.header.frame_id = self.odom_frame
        msg.child_frame_id = self.base_frame
        msg.pose.pose.position.x = st.x
        msg.pose.pose.position.y = st.y
        msg.pose.pose.orientation.z = qz
        msg.pose.pose.orientation.w = qw
        msg.twist.twist.linear.x = st.vx
        msg.twist.twist.linear.y = st.vy
        msg.twist.twist.angular.z = st.wz
        self.odom_pub.publish(msg)

        if self._tf_broadcaster is not None:
            tf = TransformStamped()
            tf.header.stamp = stamp
            tf.header.frame_id = self.odom_frame
            tf.child_frame_id = self.base_frame
            tf.transform.translation.x = st.x
            tf.transform.translation.y = st.y
            tf.transform.rotation.z = qz
            tf.transform.rotation.w = qw
            self._tf_broadcaster.sendTransform(tf)

    def stop_chassis(self) -> None:
        self._send(FrameType.STOP, pack_stop(StopReason.DEBUG_STOP))


def main(args=None) -> None:
    rclpy.init(args=args)
    node = Stm32BridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.stop_chassis()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
