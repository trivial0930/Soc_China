#include "motion_controller.h"

#include <stdlib.h>
#include <string.h>

static int16_t clamp_i32_to_pwm(int32_t value, uint16_t max_pwm)
{
    int32_t max = (int32_t)max_pwm;
    if (value > max) {
        return (int16_t)max;
    }
    if (value < -max) {
        return (int16_t)-max;
    }
    return (int16_t)value;
}

static int32_t scale_axis(int16_t value, int16_t max_value, uint16_t max_pwm)
{
    if (max_value <= 0) {
        return 0;
    }
    return ((int32_t)value * (int32_t)max_pwm) / (int32_t)max_value;
}

static bool elapsed(uint32_t now_ms, uint32_t then_ms, uint32_t timeout_ms)
{
    return (uint32_t)(now_ms - then_ms) > timeout_ms;
}

static void apply_all(motion_controller_t *controller)
{
    if (controller->config.apply_wheel == 0) {
        return;
    }

    for (uint8_t i = 0; i < 4u; ++i) {
        controller->config.apply_wheel(i, controller->wheel_pwm[i], controller->config.user);
    }
}

static void set_all_zero(motion_controller_t *controller)
{
    memset(controller->wheel_pwm, 0, sizeof(controller->wheel_pwm));
    apply_all(controller);
}

motion_config_t motion_default_config(void)
{
    motion_config_t config;

    config.apply_wheel = 0;
    config.user = 0;
    config.max_pwm = 1000u;
    config.max_vx_mm_s = 500;
    config.max_vy_mm_s = 500;
    config.max_wz_mrad_s = 1500;
    config.cmd_timeout_ms = 500u;
    config.heartbeat_timeout_ms = 2000u;
    return config;
}

void motion_init(motion_controller_t *controller, const motion_config_t *config, uint32_t now_ms)
{
    if (controller == 0) {
        return;
    }

    memset(controller, 0, sizeof(*controller));
    controller->config = (config == 0) ? motion_default_config() : *config;
    if (controller->config.max_pwm == 0u) {
        controller->config.max_pwm = 1000u;
    }
    if (controller->config.max_vx_mm_s <= 0) {
        controller->config.max_vx_mm_s = 500;
    }
    if (controller->config.max_vy_mm_s <= 0) {
        controller->config.max_vy_mm_s = 500;
    }
    if (controller->config.max_wz_mrad_s <= 0) {
        controller->config.max_wz_mrad_s = 1500;
    }
    if (controller->config.cmd_timeout_ms == 0u) {
        controller->config.cmd_timeout_ms = 500u;
    }
    if (controller->config.heartbeat_timeout_ms == 0u) {
        controller->config.heartbeat_timeout_ms = 2000u;
    }

    controller->mode = MOTION_MODE_IDLE;
    controller->state = MOTION_STATE_IDLE;
    controller->last_cmd_ms = now_ms;
    controller->last_heartbeat_ms = now_ms;
    set_all_zero(controller);
}

motion_result_t motion_set_mode(motion_controller_t *controller, motion_mode_t mode, uint32_t now_ms)
{
    if (controller == 0) {
        return MOTION_RESULT_MODE_NOT_ALLOWED;
    }
    if (controller->estop) {
        motion_stop(controller);
        return MOTION_RESULT_ESTOP;
    }

    controller->mode = mode;
    if (mode == MOTION_MODE_IDLE) {
        controller->state = MOTION_STATE_IDLE;
        motion_stop(controller);
    }
    controller->last_heartbeat_ms = now_ms;
    return MOTION_RESULT_OK;
}

motion_result_t motion_handle_cmd_vel(
    motion_controller_t *controller,
    const motion_cmd_vel_t *cmd,
    uint32_t now_ms)
{
    int32_t vx_pwm;
    int32_t vy_pwm;
    int32_t wz_pwm;

    if ((controller == 0) || (cmd == 0)) {
        return MOTION_RESULT_MODE_NOT_ALLOWED;
    }
    if (controller->estop) {
        motion_stop(controller);
        return MOTION_RESULT_ESTOP;
    }
    if (controller->mode == MOTION_MODE_IDLE) {
        motion_stop(controller);
        return MOTION_RESULT_MODE_NOT_ALLOWED;
    }

    vx_pwm = scale_axis(cmd->vx_mm_s, controller->config.max_vx_mm_s, controller->config.max_pwm);
    vy_pwm = scale_axis(cmd->vy_mm_s, controller->config.max_vy_mm_s, controller->config.max_pwm);
    wz_pwm = scale_axis(cmd->wz_mrad_s, controller->config.max_wz_mrad_s, controller->config.max_pwm);

    controller->wheel_pwm[0] = clamp_i32_to_pwm(vx_pwm - vy_pwm - wz_pwm, controller->config.max_pwm);
    controller->wheel_pwm[1] = clamp_i32_to_pwm(vx_pwm + vy_pwm + wz_pwm, controller->config.max_pwm);
    controller->wheel_pwm[2] = clamp_i32_to_pwm(vx_pwm + vy_pwm - wz_pwm, controller->config.max_pwm);
    controller->wheel_pwm[3] = clamp_i32_to_pwm(vx_pwm - vy_pwm + wz_pwm, controller->config.max_pwm);

    controller->last_cmd_ms = now_ms;
    controller->state = MOTION_STATE_ACTIVE;
    apply_all(controller);
    return MOTION_RESULT_OK;
}

void motion_handle_heartbeat(motion_controller_t *controller, uint32_t now_ms)
{
    if (controller == 0) {
        return;
    }
    controller->last_heartbeat_ms = now_ms;
}

void motion_set_estop(motion_controller_t *controller, bool active, uint32_t now_ms)
{
    if (controller == 0) {
        return;
    }

    controller->estop = active;
    controller->last_heartbeat_ms = now_ms;
    if (active) {
        controller->state = MOTION_STATE_ESTOP;
        motion_stop(controller);
    } else {
        controller->state = MOTION_STATE_IDLE;
        motion_stop(controller);
    }
}

void motion_tick(motion_controller_t *controller, uint32_t now_ms)
{
    if (controller == 0) {
        return;
    }

    if (controller->estop) {
        controller->state = MOTION_STATE_ESTOP;
        motion_stop(controller);
        return;
    }

    if (elapsed(now_ms, controller->last_heartbeat_ms, controller->config.heartbeat_timeout_ms)) {
        controller->state = MOTION_STATE_HEARTBEAT_TIMEOUT;
        motion_stop(controller);
        return;
    }

    if ((controller->state == MOTION_STATE_ACTIVE)
        && elapsed(now_ms, controller->last_cmd_ms, controller->config.cmd_timeout_ms)) {
        controller->state = MOTION_STATE_CMD_TIMEOUT;
        motion_stop(controller);
    }
}

void motion_stop(motion_controller_t *controller)
{
    if (controller == 0) {
        return;
    }
    set_all_zero(controller);
}
