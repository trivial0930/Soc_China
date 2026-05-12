# RDK STM32 Mecanum UART Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the existing STM32 UART `CMD_VEL` path to the mecanum chassis control module without configuring unconfirmed PWM/DIR hardware pins.

**Architecture:** Keep `rdk_stm32_uart.c/h` as the pure frame/protocol layer. Add `mecanum_drive.c/h` to the CubeIDE project `Core` tree and call it from `main.c` USER CODE sections via a replaceable `write_motor` callback that currently records commands but does not drive hardware pins.

**Tech Stack:** STM32CubeIDE-generated C, STM32 HAL UART, host-side `gcc` C module tests, Python `unittest` integration checks.

---

## File Structure

- Modify: `tests/test_stm32_c_modules.py`
  - Add a host-side C test that compiles `stm32_motion_controller/Core/Src/mecanum_drive.c` and verifies velocity, stop, and timeout behavior.
- Modify: `tests/test_stm32_main_uart_integration.py`
  - Add text checks for the `main.c` integration points: `mecanum_drive.h`, chassis init, `CMD_VEL` conversion, `MecanumDrive_SetVelocity`, `MecanumDrive_Stop`, and timeout update.
- Create: `stm32/firmware/stm32_motion_controller/Core/Inc/mecanum_drive.h`
  - CubeIDE-project-local header copied from the existing standalone module.
- Create: `stm32/firmware/stm32_motion_controller/Core/Src/mecanum_drive.c`
  - CubeIDE-project-local implementation copied from the existing standalone module.
- Modify: `stm32/firmware/stm32_motion_controller/Core/Src/main.c`
  - Include `mecanum_drive.h`, add chassis state, initialize it before UART start, route `CMD_VEL` to it, and stop it on `STOP`, `IDLE`, heartbeat timeout, command timeout, and estop.
- Create: `docs/superpowers/plans/2026-05-12-rdk-stm32-mecanum-uart-integration.md`
  - This implementation plan.

## Task 1: Add Failing Tests For Project-Local Mecanum Module

**Files:**
- Modify: `tests/test_stm32_c_modules.py`
- Modify: `tests/test_stm32_main_uart_integration.py`
- Test: `tests/test_stm32_c_modules.py`
- Test: `tests/test_stm32_main_uart_integration.py`

- [ ] **Step 1: Add the failing C module test**

Append this test method inside `class Stm32CModuleTest(unittest.TestCase):` in `tests/test_stm32_c_modules.py`:

```python
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
```

- [ ] **Step 2: Add the failing `main.c` integration text checks**

Extend `required_snippets` in `tests/test_stm32_main_uart_integration.py` with:

```python
            '#include "mecanum_drive.h"',
            "static MecanumDrive app_chassis",
            "app_chassis_init()",
            "MecanumDrive_SetVelocity(&app_chassis,",
            "MecanumDrive_UpdateTimeout(&app_chassis, now)",
            "MecanumDrive_Stop(&app_chassis)",
            "app_cmd_to_chassis(&cmd)",
            "app_write_motor",
```

- [ ] **Step 3: Run tests to verify they fail for the expected reason**

Run:

```bash
python3 -m unittest tests.test_stm32_c_modules tests.test_stm32_main_uart_integration
```

Expected:

- `test_mecanum_drive_project_module_velocity_stop_and_timeout` fails because `stm32/firmware/stm32_motion_controller/Core/Src/mecanum_drive.c` does not exist yet.
- `test_main_starts_uart_rx_and_can_reply_to_rdk` fails because `main.c` does not yet include the new mecanum integration snippets.

## Task 2: Add Mecanum Module To The CubeIDE Project Tree

**Files:**
- Create: `stm32/firmware/stm32_motion_controller/Core/Inc/mecanum_drive.h`
- Create: `stm32/firmware/stm32_motion_controller/Core/Src/mecanum_drive.c`
- Test: `tests/test_stm32_c_modules.py`

- [ ] **Step 1: Copy the existing header into the CubeIDE project**

Copy the exact content from:

```text
stm32/firmware/Core/Inc/mecanum_drive.h
```

to:

```text
stm32/firmware/stm32_motion_controller/Core/Inc/mecanum_drive.h
```

- [ ] **Step 2: Copy the existing implementation into the CubeIDE project**

Copy the exact content from:

```text
stm32/firmware/Core/Src/mecanum_drive.c
```

to:

```text
stm32/firmware/stm32_motion_controller/Core/Src/mecanum_drive.c
```

- [ ] **Step 3: Run the mecanum C module test**

Run:

```bash
python3 -m unittest tests.test_stm32_c_modules.Stm32CModuleTest.test_mecanum_drive_project_module_velocity_stop_and_timeout
```

Expected: PASS.

## Task 3: Wire `main.c` UART Dispatch To The Mecanum Chassis

**Files:**
- Modify: `stm32/firmware/stm32_motion_controller/Core/Src/main.c`
- Test: `tests/test_stm32_main_uart_integration.py`

- [ ] **Step 1: Add includes and constants**

In `main.c`, add the include in `USER CODE BEGIN Includes`:

```c
#include "mecanum_drive.h"
```

Add chassis constants in `USER CODE BEGIN PD`:

```c
#define APP_CHASSIS_WHEEL_RADIUS_M 0.05f
#define APP_CHASSIS_HALF_LENGTH_M 0.12f
#define APP_CHASSIS_HALF_WIDTH_M 0.10f
#define APP_CHASSIS_MAX_WHEEL_RADPS 30.0f
#define APP_CHASSIS_PWM_MAX 999u
```

- [ ] **Step 2: Add chassis state and helper prototypes**

Add private variables in `USER CODE BEGIN PV`:

```c
static MecanumDrive app_chassis;
static volatile MecanumMotorCommand app_last_motor_command[MECANUM_WHEEL_COUNT];
```

Add prototypes in `USER CODE BEGIN PFP`:

```c
static void app_chassis_init(void);
static void app_write_motor(MecanumWheelId wheel, const MecanumMotorCommand *command, void *user);
static void app_cmd_to_chassis(const rdk_cmd_vel_t *cmd);
static void app_chassis_stop(void);
```

- [ ] **Step 3: Initialize chassis before UART receive starts**

In `USER CODE BEGIN 2`, call chassis init before `app_uart_start();`:

```c
  app_chassis_init();
  app_uart_start();
```

- [ ] **Step 4: Run chassis timeout from the main loop tick**

In `app_tick()`, after `now` is loaded, call:

```c
  MecanumDrive_UpdateTimeout(&app_chassis, now);
```

- [ ] **Step 5: Stop the chassis on fault or idle paths**

Call `app_chassis_stop();` when:

- `app_estop != 0u`
- heartbeat timeout is detected
- command timeout is detected
- `SET_MODE` selects `RDK_MODE_IDLE`
- `STOP` is received
- `CMD_VEL` is rejected due to estop or idle mode

- [ ] **Step 6: Route valid `CMD_VEL` payloads into the chassis**

In the valid `RDK_FRAME_CMD_VEL` branch, replace `(void)cmd;` with:

```c
        app_cmd_to_chassis(&cmd);
```

- [ ] **Step 7: Add helper implementations**

Add these helpers in `USER CODE BEGIN 4`:

```c
static void app_chassis_init(void)
{
  MecanumDriveConfig cfg;

  MecanumDrive_DefaultConfig(&cfg);
  cfg.wheel_radius_m = APP_CHASSIS_WHEEL_RADIUS_M;
  cfg.half_length_m = APP_CHASSIS_HALF_LENGTH_M;
  cfg.half_width_m = APP_CHASSIS_HALF_WIDTH_M;
  cfg.max_wheel_radps = APP_CHASSIS_MAX_WHEEL_RADPS;
  cfg.pwm_max = APP_CHASSIS_PWM_MAX;
  cfg.command_timeout_ms = APP_CMD_TIMEOUT_MS;
  cfg.write_motor = app_write_motor;
  cfg.user = NULL;

  (void)MecanumDrive_Init(&app_chassis, &cfg);
}

static void app_write_motor(MecanumWheelId wheel, const MecanumMotorCommand *command, void *user)
{
  (void)user;

  if ((wheel >= MECANUM_WHEEL_COUNT) || (command == NULL))
  {
    return;
  }

  app_last_motor_command[wheel] = *command;
}

static void app_cmd_to_chassis(const rdk_cmd_vel_t *cmd)
{
  if (cmd == NULL)
  {
    return;
  }

  MecanumDrive_SetVelocity(&app_chassis,
                           ((float)cmd->vx_mm_s) / 1000.0f,
                           ((float)cmd->vy_mm_s) / 1000.0f,
                           ((float)cmd->wz_mrad_s) / 1000.0f,
                           HAL_GetTick());
}

static void app_chassis_stop(void)
{
  MecanumDrive_Stop(&app_chassis);
}
```

- [ ] **Step 8: Run the `main.c` integration test**

Run:

```bash
python3 -m unittest tests.test_stm32_main_uart_integration
```

Expected: PASS.

## Task 4: Run Full Verification And Review Scope

**Files:**
- Test: all touched tests and full unittest suite

- [ ] **Step 1: Run the STM32 C module tests**

Run:

```bash
python3 -m unittest tests.test_stm32_c_modules
```

Expected: PASS.

- [ ] **Step 2: Run the full repository unittest suite**

Run:

```bash
python3 -m unittest discover -s tests
```

Expected: PASS with 10 tests or more and zero failures.

- [ ] **Step 3: Check patch formatting**

Run:

```bash
git diff --check
```

Expected: no output and exit code 0.

- [ ] **Step 4: Review changed files**

Run:

```bash
git diff --stat
git diff -- stm32/firmware/stm32_motion_controller/Core/Src/main.c tests/test_stm32_c_modules.py tests/test_stm32_main_uart_integration.py
```

Expected: only plan-relevant code, tests, and plan file changed.
