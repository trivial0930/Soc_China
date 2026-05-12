import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def shutil_which(name: str):
    import shutil

    return shutil.which(name)


class Stm32CModuleTest(unittest.TestCase):
    def compile_and_run(self, source: str, extra_sources: list[str]):
        with tempfile.TemporaryDirectory() as tmp:
            main_c = Path(tmp) / "main.c"
            main_c.write_text(textwrap.dedent(source), encoding="utf-8")
            exe = Path(tmp) / "test"
            cmd = [
                "gcc",
                "-std=c99",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-I",
                str(ROOT / "stm32/firmware/stm32_motion_controller/Core/Inc"),
                str(main_c),
                *[str(ROOT / path) for path in extra_sources],
                "-o",
                str(exe),
            ]
            subprocess.run(cmd, check=True, cwd=ROOT)
            subprocess.run([str(exe)], check=True, cwd=ROOT)

    @unittest.skipIf(not shutil_which("gcc"), "gcc is required for C module tests")
    def test_protocol_c_module_encodes_and_parses_frames(self):
        self.compile_and_run(
            r"""
            #include <assert.h>
            #include <stdint.h>
            #include <string.h>
            #include "rdk_stm32_uart.h"

            int main(void) {
                const uint8_t vector[] = "123456789";
                assert(rdk_crc16_ccitt_false(vector, 9) == 0x29B1u);

                uint8_t payload[4];
                rdk_pack_heartbeat(payload, 1000u);

                uint8_t raw[80];
                int encoded = rdk_encode_frame(RDK_FRAME_HEARTBEAT, 7u, payload, 4u, raw, sizeof(raw));
                assert(encoded == 12);
                assert(raw[0] == 0xAA && raw[1] == 0x55);
                assert(raw[2] == 0x01 && raw[3] == RDK_FRAME_HEARTBEAT && raw[4] == 7u && raw[5] == 4u);

                rdk_parser_t parser;
                rdk_frame_t frame;
                rdk_parser_init(&parser);
                for (int i = 0; i < encoded - 1; ++i) {
                    assert(rdk_parser_feed(&parser, raw[i], &frame) == RDK_PARSE_NONE);
                }
                assert(rdk_parser_feed(&parser, raw[encoded - 1], &frame) == RDK_PARSE_FRAME_READY);
                assert(frame.type == RDK_FRAME_HEARTBEAT);
                assert(frame.seq == 7u);
                assert(frame.len == 4u);
                assert(memcmp(frame.payload, payload, 4u) == 0);

                uint8_t cmd_payload[6];
                rdk_cmd_vel_t cmd = { .vx_mm_s = 50, .vy_mm_s = -25, .wz_mrad_s = 100 };
                rdk_pack_cmd_vel(cmd_payload, &cmd);
                rdk_cmd_vel_t decoded;
                assert(rdk_unpack_cmd_vel(cmd_payload, 6u, &decoded) == 0);
                assert(decoded.vx_mm_s == 50);
                assert(decoded.vy_mm_s == -25);
                assert(decoded.wz_mrad_s == 100);

                raw[encoded - 1] ^= 0xFFu;
                rdk_parser_init(&parser);
                rdk_parse_result_t result = RDK_PARSE_NONE;
                for (int i = 0; i < encoded; ++i) {
                    result = rdk_parser_feed(&parser, raw[i], &frame);
                }
                assert(result == RDK_PARSE_CRC_ERROR);
                assert(parser.crc_error_count == 1u);
                return 0;
            }
            """,
            ["stm32/firmware/stm32_motion_controller/Core/Src/rdk_stm32_uart.c"],
        )

    @unittest.skipIf(not shutil_which("gcc"), "gcc is required for C module tests")
    def test_motion_controller_stops_on_timeout_and_estop(self):
        self.compile_and_run(
            r"""
            #include <assert.h>
            #include <stdint.h>
            #include "motion_controller.h"

            static int16_t applied[4];
            static uint8_t apply_count;

            static void capture_apply(uint8_t wheel, int16_t pwm, void *user) {
                (void)user;
                assert(wheel < 4u);
                applied[wheel] = pwm;
                apply_count++;
            }

            static int all_zero(void) {
                return applied[0] == 0 && applied[1] == 0 && applied[2] == 0 && applied[3] == 0;
            }

            int main(void) {
                motion_config_t config = motion_default_config();
                config.apply_wheel = capture_apply;
                config.max_pwm = 1000u;

                motion_controller_t controller;
                motion_init(&controller, &config, 0u);
                assert(controller.mode == MOTION_MODE_IDLE);
                assert(all_zero());

                assert(motion_set_mode(&controller, MOTION_MODE_MANUAL, 10u) == MOTION_RESULT_OK);
                motion_cmd_vel_t cmd = { .vx_mm_s = 50, .vy_mm_s = 0, .wz_mrad_s = 0 };
                assert(motion_handle_cmd_vel(&controller, &cmd, 20u) == MOTION_RESULT_OK);
                assert(controller.state == MOTION_STATE_ACTIVE);
                assert(applied[0] > 0 && applied[1] > 0 && applied[2] > 0 && applied[3] > 0);

                motion_tick(&controller, 621u);
                assert(controller.state == MOTION_STATE_CMD_TIMEOUT);
                assert(all_zero());

                assert(motion_handle_cmd_vel(&controller, &cmd, 700u) == MOTION_RESULT_OK);
                motion_set_estop(&controller, true, 710u);
                assert(controller.state == MOTION_STATE_ESTOP);
                assert(controller.estop);
                assert(all_zero());
                assert(motion_handle_cmd_vel(&controller, &cmd, 720u) == MOTION_RESULT_ESTOP);

                motion_set_estop(&controller, false, 900u);
                assert(controller.state == MOTION_STATE_IDLE);
                assert(all_zero());
                assert(apply_count >= 12u);
                return 0;
            }
            """,
            [
                "stm32/firmware/stm32_motion_controller/Core/Src/motion_controller.c",
            ],
        )

    @unittest.skipIf(not shutil_which("gcc"), "gcc is required for C module tests")
    def test_mecanum_drive_project_module_velocity_stop_and_timeout(self):
        self.compile_and_run(
            r"""
            #include <assert.h>
            #include <stdint.h>
            #include "mecanum_drive.h"

            static MecanumMotorCommand applied[MECANUM_WHEEL_COUNT];
            static uint8_t apply_count;

            static void capture_motor(MecanumWheelId wheel, const MecanumMotorCommand *command, void *user) {
                (void)user;
                assert(wheel < MECANUM_WHEEL_COUNT);
                assert(command != 0);
                applied[wheel] = *command;
                apply_count++;
            }

            static int all_pwm_zero(void) {
                return applied[MECANUM_WHEEL_LF].pwm == 0u
                    && applied[MECANUM_WHEEL_RF].pwm == 0u
                    && applied[MECANUM_WHEEL_LR].pwm == 0u
                    && applied[MECANUM_WHEEL_RR].pwm == 0u;
            }

            int main(void) {
                MecanumDriveConfig config;
                MecanumDrive chassis;

                MecanumDrive_DefaultConfig(&config);
                config.write_motor = capture_motor;
                config.pwm_max = 1000u;
                config.command_timeout_ms = 500u;

                assert(MecanumDrive_Init(&chassis, &config) == 1u);
                assert(all_pwm_zero());

                MecanumDrive_SetVelocity(&chassis, 0.05f, 0.0f, 0.0f, 10u);
                assert(chassis.timed_out == 0u);
                assert(applied[MECANUM_WHEEL_LF].pwm > 0u);
                assert(applied[MECANUM_WHEEL_RF].pwm > 0u);
                assert(applied[MECANUM_WHEEL_LR].pwm > 0u);
                assert(applied[MECANUM_WHEEL_RR].pwm > 0u);

                MecanumDrive_Stop(&chassis);
                assert(all_pwm_zero());

                MecanumDrive_SetVelocity(&chassis, 0.05f, 0.0f, 0.0f, 100u);
                MecanumDrive_UpdateTimeout(&chassis, 600u);
                assert(chassis.timed_out == 1u);
                assert(all_pwm_zero());
                assert(apply_count >= 16u);
                return 0;
            }
            """,
            ["stm32/firmware/stm32_motion_controller/Core/Src/mecanum_drive.c"],
        )
if __name__ == "__main__":
    unittest.main()
