import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INC = ROOT / "stm32/firmware/stm32_motion_controller/Core/Inc"
SRC = ROOT / "stm32/firmware/stm32_motion_controller/Core/Src/wheel_pid.c"


class WheelPidTest(unittest.TestCase):
    def compile_and_run(self, source: str):
        with tempfile.TemporaryDirectory() as tmp:
            main_c = Path(tmp) / "main.c"
            main_c.write_text(textwrap.dedent(source), encoding="utf-8")
            exe = Path(tmp) / "test"
            cmd = [
                "gcc", "-std=c99", "-Wall", "-Wextra", "-Werror",
                "-I", str(INC), str(main_c), str(SRC), "-lm", "-o", str(exe),
            ]
            subprocess.run(cmd, check=True, cwd=ROOT)
            subprocess.run([str(exe)], check=True, cwd=ROOT)

    @unittest.skipIf(not shutil.which("gcc"), "gcc required")
    def test_feedforward_only_reproduces_open_loop(self):
        self.compile_and_run(
            r"""
            #include <assert.h>
            #include <math.h>
            #include "wheel_pid.h"

            int main(void) {
                /* ff = pwm_max/max_radps = 999/30 = 33.3; gains 0 -> pure FF */
                WheelPidConfig cfg = {0};
                cfg.ff = 999.0f / 30.0f;
                cfg.out_min = -999.0f; cfg.out_max = 999.0f;
                cfg.integral_min = -500.0f; cfg.integral_max = 500.0f;
                WheelPid pid; WheelPid_Init(&pid, &cfg);

                /* setpoint 15 rad/s, measured irrelevant for FF, gains 0 */
                float u = WheelPid_Update(&pid, 15.0f, 3.0f, 0.02f);
                assert(fabsf(u - cfg.ff * 15.0f) < 1e-3f);
                return 0;
            }
            """
        )

    @unittest.skipIf(not shutil.which("gcc"), "gcc required")
    def test_p_term_drives_toward_setpoint(self):
        self.compile_and_run(
            r"""
            #include <assert.h>
            #include <math.h>
            #include "wheel_pid.h"

            int main(void) {
                WheelPidConfig cfg = {0};
                cfg.kp = 2.0f;
                cfg.out_min = -1000.0f; cfg.out_max = 1000.0f;
                cfg.integral_min = -1000.0f; cfg.integral_max = 1000.0f;
                WheelPid pid; WheelPid_Init(&pid, &cfg);

                /* error = 10-4 = 6 -> p = 12, no ff/i/d on first step */
                float u = WheelPid_Update(&pid, 10.0f, 4.0f, 0.02f);
                assert(fabsf(u - 12.0f) < 1e-3f);

                /* negative error -> negative output */
                WheelPid_Reset(&pid);
                float u2 = WheelPid_Update(&pid, 2.0f, 9.0f, 0.02f);
                assert(u2 < 0.0f);
                return 0;
            }
            """
        )

    @unittest.skipIf(not shutil.which("gcc"), "gcc required")
    def test_output_is_clamped(self):
        self.compile_and_run(
            r"""
            #include <assert.h>
            #include "wheel_pid.h"

            int main(void) {
                WheelPidConfig cfg = {0};
                cfg.ff = 1000.0f;
                cfg.out_min = -999.0f; cfg.out_max = 999.0f;
                WheelPid pid; WheelPid_Init(&pid, &cfg);
                float u = WheelPid_Update(&pid, 5.0f, 0.0f, 0.02f); /* 5000 -> clamp */
                assert(u == 999.0f);
                float v = WheelPid_Update(&pid, -5.0f, 0.0f, 0.02f);
                assert(v == -999.0f);
                return 0;
            }
            """
        )

    @unittest.skipIf(not shutil.which("gcc"), "gcc required")
    def test_integral_clamped_and_antiwindup(self):
        self.compile_and_run(
            r"""
            #include <assert.h>
            #include <math.h>
            #include "wheel_pid.h"

            int main(void) {
                WheelPidConfig cfg = {0};
                cfg.ki = 1.0f;
                cfg.out_min = -50.0f; cfg.out_max = 50.0f;   /* tight output clamp */
                cfg.integral_min = -100.0f; cfg.integral_max = 100.0f;
                WheelPid pid; WheelPid_Init(&pid, &cfg);

                /* constant positive error, output saturates at +50 quickly;
                   integral must not exceed its clamp and output stays clamped */
                float u = 0.0f;
                for (int i = 0; i < 200; ++i) {
                    u = WheelPid_Update(&pid, 10.0f, 0.0f, 0.05f);
                }
                assert(u == 50.0f);
                assert(pid.integral <= 100.0f + 1e-3f);

                /* now reverse: large negative error should unwind integral */
                for (int i = 0; i < 200; ++i) {
                    u = WheelPid_Update(&pid, -10.0f, 0.0f, 0.05f);
                }
                assert(u == -50.0f);
                assert(pid.integral >= -100.0f - 1e-3f);
                return 0;
            }
            """
        )

    @unittest.skipIf(not shutil.which("gcc"), "gcc required")
    def test_reset_clears_state(self):
        self.compile_and_run(
            r"""
            #include <assert.h>
            #include "wheel_pid.h"

            int main(void) {
                WheelPidConfig cfg = {0};
                cfg.ki = 1.0f; cfg.kd = 1.0f;
                cfg.out_min = -1000.0f; cfg.out_max = 1000.0f;
                cfg.integral_min = -1000.0f; cfg.integral_max = 1000.0f;
                WheelPid pid; WheelPid_Init(&pid, &cfg);
                WheelPid_Update(&pid, 5.0f, 0.0f, 0.02f);
                WheelPid_Update(&pid, 5.0f, 0.0f, 0.02f);
                assert(pid.integral != 0.0f);
                WheelPid_Reset(&pid);
                assert(pid.integral == 0.0f);
                assert(pid.has_prev == 0u);
                return 0;
            }
            """
        )


if __name__ == "__main__":
    unittest.main()
