#ifndef MOTION_CONTROLLER_H
#define MOTION_CONTROLLER_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    MOTION_MODE_IDLE = 0,
    MOTION_MODE_MANUAL = 1,
    MOTION_MODE_AUTO = 2,
    MOTION_MODE_TEST = 3
} motion_mode_t;

typedef enum {
    MOTION_STATE_IDLE = 0,
    MOTION_STATE_ACTIVE = 1,
    MOTION_STATE_CMD_TIMEOUT = 2,
    MOTION_STATE_HEARTBEAT_TIMEOUT = 3,
    MOTION_STATE_ESTOP = 4
} motion_state_t;

typedef enum {
    MOTION_RESULT_OK = 0,
    MOTION_RESULT_ESTOP = -1,
    MOTION_RESULT_MODE_NOT_ALLOWED = -2
} motion_result_t;

typedef struct {
    int16_t vx_mm_s;
    int16_t vy_mm_s;
    int16_t wz_mrad_s;
} motion_cmd_vel_t;

typedef void (*motion_apply_wheel_fn)(uint8_t wheel, int16_t pwm, void *user);

typedef struct {
    motion_apply_wheel_fn apply_wheel;
    void *user;
    uint16_t max_pwm;
    int16_t max_vx_mm_s;
    int16_t max_vy_mm_s;
    int16_t max_wz_mrad_s;
    uint32_t cmd_timeout_ms;
    uint32_t heartbeat_timeout_ms;
} motion_config_t;

typedef struct {
    motion_config_t config;
    motion_mode_t mode;
    motion_state_t state;
    bool estop;
    uint32_t last_cmd_ms;
    uint32_t last_heartbeat_ms;
    int16_t wheel_pwm[4];
} motion_controller_t;

motion_config_t motion_default_config(void);
void motion_init(motion_controller_t *controller, const motion_config_t *config, uint32_t now_ms);
motion_result_t motion_set_mode(motion_controller_t *controller, motion_mode_t mode, uint32_t now_ms);
motion_result_t motion_handle_cmd_vel(
    motion_controller_t *controller,
    const motion_cmd_vel_t *cmd,
    uint32_t now_ms);
void motion_handle_heartbeat(motion_controller_t *controller, uint32_t now_ms);
void motion_set_estop(motion_controller_t *controller, bool active, uint32_t now_ms);
void motion_tick(motion_controller_t *controller, uint32_t now_ms);
void motion_stop(motion_controller_t *controller);

#ifdef __cplusplus
}
#endif

#endif
