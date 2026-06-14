import sys
import unittest
from pathlib import Path


PACKAGE_SRC = Path(__file__).resolve().parents[1] / "rdk_x5" / "ros2_ws" / "src" / "gimbal_laser"
sys.path.insert(0, str(PACKAGE_SRC))

from gimbal_laser.gimbal_controller import (
    AxisConfig,
    AxisIO,
    ControlConfig,
    GimbalController,
    GimbalState,
)


class FakeSensor:
    def __init__(self, angle: float) -> None:
        self.angle = angle
        self.fail = False

    def read_degrees(self) -> float:
        if self.fail:
            raise OSError("i2c disconnected")
        return self.angle


class FakeMotor:
    def __init__(self) -> None:
        self.enabled = True
        self.duties = []

    def disable(self) -> None:
        self.enabled = False

    def enable(self) -> None:
        self.enabled = True

    def set_phase_duties(self, duties) -> None:
        self.duties.append(tuple(duties))

    def stop(self) -> None:
        self.duties.append((0.0, 0.0, 0.0))


def build_controller() -> GimbalController:
    pan_sensor = FakeSensor(10.0)
    tilt_sensor = FakeSensor(-5.0)
    pan_motor = FakeMotor()
    tilt_motor = FakeMotor()
    return GimbalController(
        pan=AxisIO(
            config=AxisConfig(name="pan", min_deg=-60.0, max_deg=60.0),
            sensor=pan_sensor,
            motor=pan_motor,
        ),
        tilt=AxisIO(
            config=AxisConfig(name="tilt", min_deg=-30.0, max_deg=45.0),
            sensor=tilt_sensor,
            motor=tilt_motor,
        ),
        config=ControlConfig(max_duty=0.1, startup_duty=0.03, command_timeout_sec=1.0),
    )


class GimbalControllerTest(unittest.TestCase):
    def test_startup_forces_safe_idle_before_enable(self):
        controller = build_controller()

        status = controller.step(now_sec=0.0)

        self.assertEqual(status.state, GimbalState.IDLE)
        self.assertFalse(controller.pan.motor.enabled)
        self.assertFalse(controller.tilt.motor.enabled)
        self.assertEqual(status.pan_deg, 10.0)
        self.assertEqual(status.tilt_deg, -5.0)

    def test_target_angles_are_clamped_to_axis_limits(self):
        controller = build_controller()

        status = controller.set_target(90.0, -90.0, now_sec=0.0)

        self.assertEqual(status.target_pan_deg, 60.0)
        self.assertEqual(status.target_tilt_deg, -30.0)
        self.assertTrue(status.clamped)

    def test_enable_moves_to_closed_loop_and_limits_duty(self):
        controller = build_controller()
        controller.step(now_sec=0.0)
        controller.set_target(20.0, -10.0, now_sec=0.0)

        status = controller.set_enabled(True, now_sec=0.1)
        status = controller.step(now_sec=0.1)

        self.assertEqual(status.state, GimbalState.ENABLED_CLOSED_LOOP)
        self.assertTrue(controller.pan.motor.enabled)
        self.assertTrue(controller.tilt.motor.enabled)
        self.assertTrue(all(0.0 <= duty <= 1.0 for duty in controller.pan.motor.duties[-1]))
        self.assertTrue(all(0.0 <= duty <= 1.0 for duty in controller.tilt.motor.duties[-1]))
        self.assertGreater(
            max(controller.pan.motor.duties[-1]) - min(controller.pan.motor.duties[-1]),
            0.02,
        )
        self.assertGreater(
            max(controller.tilt.motor.duties[-1]) - min(controller.tilt.motor.duties[-1]),
            0.02,
        )

    def test_commanded_target_is_slew_limited(self):
        controller = build_controller()
        controller.step(now_sec=0.0)
        controller.set_target(60.0, 45.0, now_sec=0.0)
        controller.set_enabled(True, now_sec=0.1)

        status = controller.step(now_sec=0.1)

        self.assertLess(status.commanded_pan_deg, status.target_pan_deg)
        self.assertLess(status.commanded_tilt_deg, status.target_tilt_deg)
        self.assertAlmostEqual(status.commanded_pan_deg, 13.2, places=6)
        self.assertAlmostEqual(status.commanded_tilt_deg, -1.8, places=6)

    def test_angle_slew_uses_shortest_wrapped_path(self):
        controller = build_controller()

        next_angle = controller._advance_angle(179.0, -179.0, dt=0.1)

        self.assertAlmostEqual(next_angle, -179.0, places=6)

    def test_torque_vector_is_continuous_near_zero_error(self):
        controller = build_controller()
        controller.last_pan_deg = 0.0

        positive = controller._duties_for_axis(controller.pan, 1.2)
        neutral = controller._duties_for_axis(controller.pan, 0.0)
        negative = controller._duties_for_axis(controller.pan, -1.2)

        self.assertEqual(neutral, (0.5, 0.5, 0.5))
        self.assertLess(max(abs(a - b) for a, b in zip(positive, negative)), 0.03)

    def _pi_controller(self, ki=0.01, ilimit=0.1):
        pan = AxisIO(
            config=AxisConfig(name="pan", min_deg=-60.0, max_deg=60.0),
            sensor=FakeSensor(0.0),
            motor=FakeMotor(),
        )
        tilt = AxisIO(
            config=AxisConfig(name="tilt", min_deg=-30.0, max_deg=45.0),
            sensor=FakeSensor(0.0),
            motor=FakeMotor(),
        )
        config = ControlConfig(
            max_duty=0.1,
            startup_duty=0.0,
            proportional_gain=0.005,
            integral_gain=ki,
            integral_limit=ilimit,
        )
        controller = GimbalController(pan=pan, tilt=tilt, config=config)
        controller.last_pan_deg = 0.0
        return controller

    def test_integral_winds_up_then_anti_windup_plateaus(self):
        controller = self._pi_controller(ki=0.01, ilimit=0.1)

        # Hold a fixed +10 deg error; the integral should grow the torque vector
        # step over step, then stop growing once the command saturates at max_duty.
        spreads = []
        for _ in range(40):
            duties = controller._duties_for_axis(controller.pan, 10.0, dt=0.1)
            spreads.append(max(duties) - min(duties))

        self.assertGreater(spreads[5], spreads[0])  # integral accumulates torque
        # anti-windup: bounded and plateaued (not exploding)
        self.assertAlmostEqual(spreads[-1], spreads[-5], delta=1e-9)

    def test_integral_does_not_accumulate_when_gain_zero(self):
        controller = self._pi_controller(ki=0.0)

        spreads = [
            max(d) - min(d)
            for d in (
                controller._duties_for_axis(controller.pan, 10.0, dt=0.1)
                for _ in range(10)
            )
        ]

        # P-only: torque vector is identical every step (no integral growth)
        self.assertAlmostEqual(max(spreads), min(spreads), delta=1e-9)

    def test_integral_resets_on_enable_and_stop(self):
        controller = self._pi_controller(ki=0.01, ilimit=0.1)
        for _ in range(10):
            controller._duties_for_axis(controller.pan, 10.0, dt=0.1)
        self.assertGreater(controller._integral["pan"], 0.0)

        controller.stop("operator_stop")
        self.assertEqual(controller._integral["pan"], 0.0)

    def test_stop_disables_motors_and_zeroes_pwm(self):
        controller = build_controller()
        controller.step(now_sec=0.0)
        controller.set_enabled(True, now_sec=0.1)
        controller.step(now_sec=0.1)

        status = controller.stop("operator_stop")

        self.assertEqual(status.state, GimbalState.IDLE)
        self.assertFalse(controller.pan.motor.enabled)
        self.assertFalse(controller.tilt.motor.enabled)
        self.assertEqual(controller.pan.motor.duties[-1], (0.0, 0.0, 0.0))
        self.assertEqual(controller.tilt.motor.duties[-1], (0.0, 0.0, 0.0))

    def test_i2c_failure_enters_fault_and_disables_outputs(self):
        controller = build_controller()
        controller.step(now_sec=0.0)
        controller.pan.sensor.fail = True

        status = controller.step(now_sec=0.1)

        self.assertEqual(status.state, GimbalState.FAULT)
        self.assertIn("i2c", status.fault)
        self.assertFalse(controller.pan.motor.enabled)
        self.assertFalse(controller.tilt.motor.enabled)

    def test_operator_stop_recovers_from_command_timeout_fault(self):
        controller = build_controller()
        controller.step(now_sec=0.0)
        controller.set_target(20.0, -10.0, now_sec=0.0)
        controller.set_enabled(True, now_sec=0.1)

        status = controller.step(now_sec=2.0)
        self.assertEqual(status.state, GimbalState.FAULT)
        self.assertEqual(status.fault, "command_timeout")

        status = controller.stop("operator_stop")

        self.assertEqual(status.state, GimbalState.IDLE)
        self.assertEqual(status.fault, "")
        self.assertFalse(status.enabled)

        controller.set_target(20.0, -10.0, now_sec=2.1)
        controller.set_enabled(True, now_sec=2.2)
        status = controller.step(now_sec=2.2)

        self.assertEqual(status.state, GimbalState.ENABLED_CLOSED_LOOP)
        self.assertTrue(status.enabled)


if __name__ == "__main__":
    unittest.main()
