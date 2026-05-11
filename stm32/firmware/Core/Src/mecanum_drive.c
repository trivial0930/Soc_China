#include "mecanum_drive.h"

#include <stddef.h>

static float absf_local(float value)
{
    return (value >= 0.0f) ? value : -value;
}

static float clampf_local(float value, float min_value, float max_value)
{
    if (value < min_value) {
        return min_value;
    }

    if (value > max_value) {
        return max_value;
    }

    return value;
}

static uint32_t elapsed_ms(uint32_t now_ms, uint32_t last_ms)
{
    return now_ms - last_ms;
}

static void write_all(MecanumDrive *drive)
{
    uint8_t i;

    if ((drive == NULL) || (drive->cfg.write_motor == NULL)) {
        return;
    }

    for (i = 0U; i < (uint8_t)MECANUM_WHEEL_COUNT; i++) {
        drive->cfg.write_motor((MecanumWheelId)i, &drive->last_command[i], drive->cfg.user);
    }
}

static void fill_stop_command(MecanumDrive *drive)
{
    uint8_t i;

    if (drive == NULL) {
        return;
    }

    for (i = 0U; i < (uint8_t)MECANUM_WHEEL_COUNT; i++) {
        drive->last_command[i].pwm = 0U;
        drive->last_command[i].dir = MECANUM_DIR_STOP;
    }
}

void MecanumDrive_DefaultConfig(MecanumDriveConfig *config)
{
    uint8_t i;

    if (config == NULL) {
        return;
    }

    config->wheel_radius_m = 0.05f;
    config->half_length_m = 0.12f;
    config->half_width_m = 0.10f;
    config->max_wheel_radps = 30.0f;
    config->pwm_max = 999U;
    config->pwm_deadband = 0U;
    config->command_timeout_ms = 2000U;
    config->write_motor = NULL;
    config->user = NULL;

    for (i = 0U; i < (uint8_t)MECANUM_WHEEL_COUNT; i++) {
        config->invert[i] = 1;
    }
}

uint8_t MecanumDrive_Init(MecanumDrive *drive, const MecanumDriveConfig *config)
{
    if ((drive == NULL) || (config == NULL)) {
        return 0U;
    }

    if ((config->wheel_radius_m <= 0.0f) ||
        (config->max_wheel_radps <= 0.0f) ||
        (config->pwm_max == 0U) ||
        (config->write_motor == NULL)) {
        return 0U;
    }

    drive->cfg = *config;
    drive->enabled = 1U;
    drive->timed_out = 0U;
    drive->last_command_ms = 0U;
    fill_stop_command(drive);
    write_all(drive);

    return 1U;
}

void MecanumDrive_Enable(MecanumDrive *drive, uint8_t enabled)
{
    if (drive == NULL) {
        return;
    }

    drive->enabled = (enabled != 0U) ? 1U : 0U;

    if (drive->enabled == 0U) {
        MecanumDrive_Stop(drive);
    }
}

void MecanumDrive_Stop(MecanumDrive *drive)
{
    if (drive == NULL) {
        return;
    }

    fill_stop_command(drive);
    write_all(drive);
}

void MecanumDrive_UpdateTimeout(MecanumDrive *drive, uint32_t now_ms)
{
    if ((drive == NULL) || (drive->cfg.command_timeout_ms == 0U)) {
        return;
    }

    if (elapsed_ms(now_ms, drive->last_command_ms) >= drive->cfg.command_timeout_ms) {
        drive->timed_out = 1U;
        MecanumDrive_Stop(drive);
    }
}

void MecanumDrive_SetVelocity(MecanumDrive *drive,
                              float vx_mps,
                              float vy_mps,
                              float wz_radps,
                              uint32_t now_ms)
{
    float wheel_radps[MECANUM_WHEEL_COUNT];

    if (drive == NULL) {
        return;
    }

    MecanumDrive_Mix(vx_mps, vy_mps, wz_radps, &drive->cfg, wheel_radps);
    MecanumDrive_SetWheelSpeeds(drive, wheel_radps, now_ms);
}

void MecanumDrive_SetWheelSpeeds(MecanumDrive *drive,
                                 const float wheel_radps[MECANUM_WHEEL_COUNT],
                                 uint32_t now_ms)
{
    uint8_t i;
    float max_abs = 0.0f;
    float scale = 1.0f;

    if ((drive == NULL) || (wheel_radps == NULL)) {
        return;
    }

    drive->last_command_ms = now_ms;
    drive->timed_out = 0U;

    if (drive->enabled == 0U) {
        MecanumDrive_Stop(drive);
        return;
    }

    for (i = 0U; i < (uint8_t)MECANUM_WHEEL_COUNT; i++) {
        float value_abs = absf_local(wheel_radps[i]);

        if (value_abs > max_abs) {
            max_abs = value_abs;
        }
    }

    if (max_abs > drive->cfg.max_wheel_radps) {
        scale = drive->cfg.max_wheel_radps / max_abs;
    }

    for (i = 0U; i < (uint8_t)MECANUM_WHEEL_COUNT; i++) {
        float radps = clampf_local(wheel_radps[i] * scale,
                                   -drive->cfg.max_wheel_radps,
                                   drive->cfg.max_wheel_radps);
        float duty_ratio = absf_local(radps) / drive->cfg.max_wheel_radps;
        uint16_t pwm = (uint16_t)(duty_ratio * (float)drive->cfg.pwm_max + 0.5f);
        int8_t invert = (drive->cfg.invert[i] < 0) ? -1 : 1;
        int8_t dir_sign = (radps >= 0.0f) ? 1 : -1;

        if (pwm < drive->cfg.pwm_deadband) {
            pwm = 0U;
        }

        drive->last_command[i].pwm = pwm;

        if (pwm == 0U) {
            drive->last_command[i].dir = MECANUM_DIR_STOP;
        } else if ((dir_sign * invert) > 0) {
            drive->last_command[i].dir = MECANUM_DIR_FORWARD;
        } else {
            drive->last_command[i].dir = MECANUM_DIR_REVERSE;
        }
    }

    write_all(drive);
}

void MecanumDrive_Mix(float vx_mps,
                      float vy_mps,
                      float wz_radps,
                      const MecanumDriveConfig *config,
                      float wheel_radps[MECANUM_WHEEL_COUNT])
{
    float radius;
    float rot;

    if ((config == NULL) || (wheel_radps == NULL) || (config->wheel_radius_m <= 0.0f)) {
        return;
    }

    radius = config->wheel_radius_m;
    rot = (config->half_length_m + config->half_width_m) * wz_radps;

    wheel_radps[MECANUM_WHEEL_LF] = (vx_mps - vy_mps - rot) / radius;
    wheel_radps[MECANUM_WHEEL_RF] = (vx_mps + vy_mps + rot) / radius;
    wheel_radps[MECANUM_WHEEL_LR] = (vx_mps + vy_mps - rot) / radius;
    wheel_radps[MECANUM_WHEEL_RR] = (vx_mps - vy_mps + rot) / radius;
}
