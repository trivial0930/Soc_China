#include "wheel_pid.h"

#include <stddef.h>

static float clampf(float v, float lo, float hi)
{
    if (v < lo) {
        return lo;
    }
    if (v > hi) {
        return hi;
    }
    return v;
}

void WheelPid_Init(WheelPid *pid, const WheelPidConfig *cfg)
{
    if ((pid == NULL) || (cfg == NULL)) {
        return;
    }
    pid->cfg = *cfg;
    WheelPid_Reset(pid);
}

void WheelPid_Reset(WheelPid *pid)
{
    if (pid == NULL) {
        return;
    }
    pid->integral = 0.0f;
    pid->prev_error = 0.0f;
    pid->has_prev = 0u;
}

float WheelPid_Update(WheelPid *pid, float setpoint, float measured, float dt)
{
    float error;
    float deriv = 0.0f;
    float candidate_integral;
    float ff_term;
    float p_term;
    float output_unsat;
    float output;

    if ((pid == NULL) || (dt <= 0.0f)) {
        return 0.0f;
    }

    error = setpoint - measured;

    ff_term = pid->cfg.ff * setpoint;
    p_term = pid->cfg.kp * error;

    if (pid->has_prev != 0u) {
        deriv = (error - pid->prev_error) / dt;
    }
    pid->prev_error = error;
    pid->has_prev = 1u;

    /* Tentative integral, clamped to its own band. */
    candidate_integral = pid->integral + error * dt;
    candidate_integral = clampf(candidate_integral,
                                pid->cfg.integral_min,
                                pid->cfg.integral_max);

    output_unsat = ff_term + p_term
                 + pid->cfg.ki * candidate_integral
                 + pid->cfg.kd * deriv;

    output = clampf(output_unsat, pid->cfg.out_min, pid->cfg.out_max);

    /* Anti-windup: only accept the new integral if we are not saturated, or if
     * the error would unwind the saturation (opposite sign of the clamp). */
    if (output_unsat == output) {
        pid->integral = candidate_integral;
    } else if (((output_unsat > output) && (error < 0.0f)) ||
               ((output_unsat < output) && (error > 0.0f))) {
        pid->integral = candidate_integral;
    }
    /* else: hold integral (do not wind up further) */

    return output;
}
