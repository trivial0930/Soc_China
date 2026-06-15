#ifndef WHEEL_PID_H
#define WHEEL_PID_H

/*
 * Per-wheel velocity PID with feed-forward, for closing the loop on measured
 * encoder speed (rad/s) -> PWM duty. Pure C, no HAL dependency, host-testable.
 *
 * Output model:  u = ff * setpoint + Kp*e + Ki*integral(e) + Kd*d(e)/dt
 * where e = setpoint - measured.
 *
 * With Kp=Ki=Kd=0 and ff = pwm_max / max_wheel_radps this reproduces the
 * existing open-loop mapping in mecanum_drive.c exactly, so closed loop can be
 * enabled gradually by raising the gains (which must be tuned on hardware).
 *
 * Anti-windup: the integral term is clamped, and integration is held when the
 * output is saturated and the error would push further into saturation.
 */

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    float kp;
    float ki;
    float kd;
    float ff;          /* feed-forward gain applied to the setpoint */
    float out_min;     /* output clamp (e.g. -pwm_max) */
    float out_max;     /* output clamp (e.g. +pwm_max) */
    float integral_min;
    float integral_max;
} WheelPidConfig;

typedef struct {
    WheelPidConfig cfg;
    float integral;
    float prev_error;
    uint8_t has_prev;
} WheelPid;

/* Initialise controller with a config (config is copied). */
void WheelPid_Init(WheelPid *pid, const WheelPidConfig *cfg);

/* Clear integral/derivative history (call when (re)starting or on STOP). */
void WheelPid_Reset(WheelPid *pid);

/* One control step. setpoint/measured in rad/s, dt in seconds (>0).
 * Returns the clamped control output (PWM duty, signed). */
float WheelPid_Update(WheelPid *pid, float setpoint, float measured, float dt);

#ifdef __cplusplus
}
#endif

#endif /* WHEEL_PID_H */
