#ifndef RDK_STM32_UART_H
#define RDK_STM32_UART_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define RDK_SOF0 0xAAu
#define RDK_SOF1 0x55u
#define RDK_PROTOCOL_VERSION 0x01u
#define RDK_MAX_PAYLOAD_LEN 64u
#define RDK_FRAME_OVERHEAD 8u
#define RDK_MAX_FRAME_LEN (RDK_MAX_PAYLOAD_LEN + RDK_FRAME_OVERHEAD)

typedef enum {
    RDK_FRAME_HEARTBEAT = 0x01,
    RDK_FRAME_CMD_VEL = 0x10,
    RDK_FRAME_STOP = 0x11,
    RDK_FRAME_SET_MODE = 0x12,
    RDK_FRAME_STATUS = 0x81,
    RDK_FRAME_ODOM = 0x82,
    RDK_FRAME_FAULT = 0x83,
    RDK_FRAME_ACK = 0x84
} rdk_frame_type_t;

typedef enum {
    RDK_MODE_IDLE = 0x00,
    RDK_MODE_MANUAL = 0x01,
    RDK_MODE_AUTO = 0x02,
    RDK_MODE_TEST = 0x03
} rdk_mode_t;

typedef enum {
    RDK_COMM_OK = 0x00,
    RDK_COMM_CMD_TIMEOUT = 0x01,
    RDK_COMM_HEARTBEAT_TIMEOUT = 0x02,
    RDK_COMM_CRC_ERROR_LIMIT = 0x03
} rdk_comm_state_t;

typedef enum {
    RDK_ACK_OK = 0x00,
    RDK_ACK_CRC_ERROR = 0x01,
    RDK_ACK_LEN_ERROR = 0x02,
    RDK_ACK_UNSUPPORTED_TYPE = 0x03,
    RDK_ACK_MODE_NOT_ALLOWED = 0x04,
    RDK_ACK_ESTOP_ACTIVE = 0x05,
    RDK_ACK_CLAMPED = 0x06
} rdk_ack_result_t;

typedef enum {
    RDK_PARSE_NONE = 0,
    RDK_PARSE_FRAME_READY = 1,
    RDK_PARSE_CRC_ERROR = -1,
    RDK_PARSE_LEN_ERROR = -2,
    RDK_PARSE_VERSION_ERROR = -3
} rdk_parse_result_t;

typedef struct {
    int16_t vx_mm_s;
    int16_t vy_mm_s;
    int16_t wz_mrad_s;
} rdk_cmd_vel_t;

typedef struct {
    uint8_t mode;
    uint8_t estop;
    uint16_t fault_code;
    uint16_t battery_mv;
    uint8_t last_cmd_seq;
    uint8_t comm_state;
} rdk_status_t;

typedef struct {
    uint8_t ack_type;
    uint8_t ack_seq;
    uint8_t result;
} rdk_ack_t;

typedef struct {
    uint8_t type;
    uint8_t seq;
    uint8_t len;
    uint8_t payload[RDK_MAX_PAYLOAD_LEN];
} rdk_frame_t;

typedef struct {
    uint8_t raw[RDK_MAX_FRAME_LEN];
    uint8_t index;
    uint8_t expected_len;
    uint32_t crc_error_count;
    uint32_t len_error_count;
    uint32_t version_error_count;
} rdk_parser_t;

uint16_t rdk_crc16_ccitt_false(const uint8_t *data, uint16_t len);

int rdk_encode_frame(
    uint8_t type,
    uint8_t seq,
    const uint8_t *payload,
    uint8_t payload_len,
    uint8_t *out,
    uint16_t out_size);

void rdk_parser_init(rdk_parser_t *parser);
rdk_parse_result_t rdk_parser_feed(rdk_parser_t *parser, uint8_t byte, rdk_frame_t *frame);

void rdk_pack_heartbeat(uint8_t out[4], uint32_t uptime_ms);
int rdk_unpack_heartbeat(const uint8_t *payload, uint8_t len, uint32_t *uptime_ms);

void rdk_pack_cmd_vel(uint8_t out[6], const rdk_cmd_vel_t *cmd);
int rdk_unpack_cmd_vel(const uint8_t *payload, uint8_t len, rdk_cmd_vel_t *cmd);

void rdk_pack_status(uint8_t out[8], const rdk_status_t *status);
void rdk_pack_ack(uint8_t out[3], const rdk_ack_t *ack);
void rdk_pack_odom(uint8_t out[8], int16_t lf, int16_t rf, int16_t lr, int16_t rr);
void rdk_pack_fault(uint8_t out[4], uint16_t fault_code, uint16_t detail);

#ifdef __cplusplus
}
#endif

#endif
