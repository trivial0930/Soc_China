#ifndef MECANUM_DRIVE_H
#define MECANUM_DRIVE_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum
{
    MECANUM_WHEEL_LF = 0,
    MECANUM_WHEEL_RF,
    MECANUM_WHEEL_LR,
    MECANUM_WHEEL_RR,
    MECANUM_WHEEL_COUNT
} MecanumWheelId;

typedef enum
{
    MECANUM_DIR_STOP = 0,
    MECANUM_DIR_FORWARD = 1,
    MECANUM_DIR_REVERSE = -1
} MecanumMotorDir;

typedef struct
{
    uint16_t pwm;
    MecanumMotorDir dir;
} MecanumMotorCommand;

typedef void (*MecanumMotorWriteFn)(MecanumWheelId wheel,
                                    const MecanumMotorCommand *command,
                                    void *user);

typedef struct
{
    float wheel_radius_m;
    float half_length_m;
    float half_width_m;
    float max_wheel_radps;
    uint16_t pwm_max;
    uint16_t pwm_deadband;
    uint32_t command_timeout_ms;
    int8_t invert[MECANUM_WHEEL_COUNT];
    MecanumMotorWriteFn write_motor;
    void *user;
} MecanumDriveConfig;

typedef struct
{
    MecanumDriveConfig cfg;
    MecanumMotorCommand last_command[MECANUM_WHEEL_COUNT];
    uint32_t last_command_ms;
    uint8_t enabled;
    uint8_t timed_out;
} MecanumDrive;

void MecanumDrive_DefaultConfig(MecanumDriveConfig *config);
uint8_t MecanumDrive_Init(MecanumDrive *drive, const MecanumDriveConfig *config);
void MecanumDrive_Enable(MecanumDrive *drive, uint8_t enabled);
void MecanumDrive_Stop(MecanumDrive *drive);
void MecanumDrive_UpdateTimeout(MecanumDrive *drive, uint32_t now_ms);
void MecanumDrive_SetVelocity(MecanumDrive *drive,
                              float vx_mps,
                              float vy_mps,
                              float wz_radps,
                              uint32_t now_ms);
void MecanumDrive_SetWheelSpeeds(MecanumDrive *drive,
                                 const float wheel_radps[MECANUM_WHEEL_COUNT],
                                 uint32_t now_ms);
void MecanumDrive_Mix(float vx_mps,
                      float vy_mps,
                      float wz_radps,
                      const MecanumDriveConfig *config,
                      float wheel_radps[MECANUM_WHEEL_COUNT]);

#ifdef __cplusplus
}
#endif

#endif
