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
        self.assertTrue(all(abs(duty) <= 0.1 for duty in controller.pan.motor.duties[-1]))
        self.assertTrue(all(abs(duty) <= 0.1 for duty in controller.tilt.motor.duties[-1]))

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


if __name__ == "__main__":
    unittest.main()
