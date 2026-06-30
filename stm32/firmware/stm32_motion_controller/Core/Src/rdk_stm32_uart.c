#include "rdk_stm32_uart.h"

#include <string.h>

static void put_u16(uint8_t *out, uint16_t value)
{
    out[0] = (uint8_t)(value & 0xFFu);
    out[1] = (uint8_t)((value >> 8) & 0xFFu);
}

static void put_i16(uint8_t *out, int16_t value)
{
    put_u16(out, (uint16_t)value);
}

static void put_u32(uint8_t *out, uint32_t value)
{
    out[0] = (uint8_t)(value & 0xFFu);
    out[1] = (uint8_t)((value >> 8) & 0xFFu);
    out[2] = (uint8_t)((value >> 16) & 0xFFu);
    out[3] = (uint8_t)((value >> 24) & 0xFFu);
}

static uint16_t get_u16(const uint8_t *in)
{
    return (uint16_t)((uint16_t)in[0] | ((uint16_t)in[1] << 8));
}

static int16_t get_i16(const uint8_t *in)
{
    return (int16_t)get_u16(in);
}

static uint32_t get_u32(const uint8_t *in)
{
    return (uint32_t)in[0]
        | ((uint32_t)in[1] << 8)
        | ((uint32_t)in[2] << 16)
        | ((uint32_t)in[3] << 24);
}

static void parser_reset(rdk_parser_t *parser)
{
    parser->index = 0;
    parser->expected_len = 0;
}

uint16_t rdk_crc16_ccitt_false(const uint8_t *data, uint16_t len)
{
    uint16_t crc = 0xFFFFu;

    for (uint16_t i = 0; i < len; ++i) {
        crc ^= (uint16_t)data[i] << 8;
        for (uint8_t bit = 0; bit < 8u; ++bit) {
            if ((crc & 0x8000u) != 0u) {
                crc = (uint16_t)((crc << 1) ^ 0x1021u);
            } else {
                crc = (uint16_t)(crc << 1);
            }
        }
    }

    return crc;
}

int rdk_encode_frame(
    uint8_t type,
    uint8_t seq,
    const uint8_t *payload,
    uint8_t payload_len,
    uint8_t *out,
    uint16_t out_size)
{
    uint16_t total_len;
    uint16_t crc;

    if (payload_len > RDK_MAX_PAYLOAD_LEN) {
        return -1;
    }
    if ((payload_len > 0u) && (payload == 0)) {
        return -1;
    }

    total_len = (uint16_t)RDK_FRAME_OVERHEAD + payload_len;
    if ((out == 0) || (out_size < total_len)) {
        return -1;
    }

    out[0] = RDK_SOF0;
    out[1] = RDK_SOF1;
    out[2] = RDK_PROTOCOL_VERSION;
    out[3] = type;
    out[4] = seq;
    out[5] = payload_len;
    if (payload_len > 0u) {
        memcpy(&out[6], payload, payload_len);
    }

    crc = rdk_crc16_ccitt_false(&out[2], (uint16_t)(4u + payload_len));
    put_u16(&out[6u + payload_len], crc);
    return (int)total_len;
}

void rdk_parser_init(rdk_parser_t *parser)
{
    if (parser == 0) {
        return;
    }
    memset(parser, 0, sizeof(*parser));
}

rdk_parse_result_t rdk_parser_feed(rdk_parser_t *parser, uint8_t byte, rdk_frame_t *frame)
{
    uint8_t payload_len;
    uint16_t crc_expected;
    uint16_t crc_actual;

    if ((parser == 0) || (frame == 0)) {
        return RDK_PARSE_NONE;
    }

    if (parser->index == 0u) {
        if (byte == RDK_SOF0) {
            parser->raw[0] = byte;
            parser->index = 1u;
        }
        return RDK_PARSE_NONE;
    }

    if (parser->index == 1u) {
        if (byte == RDK_SOF1) {
            parser->raw[1] = byte;
            parser->index = 2u;
        } else if (byte == RDK_SOF0) {
            parser->raw[0] = byte;
            parser->index = 1u;
        } else {
            parser_reset(parser);
        }
        return RDK_PARSE_NONE;
    }

    parser->raw[parser->index++] = byte;

    if (parser->index == 6u) {
        if (parser->raw[2] != RDK_PROTOCOL_VERSION) {
            parser->version_error_count++;
            parser_reset(parser);
            return RDK_PARSE_VERSION_ERROR;
        }

        payload_len = parser->raw[5];
        if (payload_len > RDK_MAX_PAYLOAD_LEN) {
            parser->len_error_count++;
            parser_reset(parser);
            return RDK_PARSE_LEN_ERROR;
        }
        parser->expected_len = (uint8_t)(RDK_FRAME_OVERHEAD + payload_len);
    }

    if ((parser->expected_len > 0u) && (parser->index >= parser->expected_len)) {
        payload_len = parser->raw[5];
        crc_expected = get_u16(&parser->raw[6u + payload_len]);
        crc_actual = rdk_crc16_ccitt_false(&parser->raw[2], (uint16_t)(4u + payload_len));

        if (crc_actual != crc_expected) {
            parser->crc_error_count++;
            parser_reset(parser);
            return RDK_PARSE_CRC_ERROR;
        }

        frame->type = parser->raw[3];
        frame->seq = parser->raw[4];
        frame->len = payload_len;
        if (payload_len > 0u) {
            memcpy(frame->payload, &parser->raw[6], payload_len);
        }
        parser_reset(parser);
        return RDK_PARSE_FRAME_READY;
    }

    return RDK_PARSE_NONE;
}

void rdk_pack_heartbeat(uint8_t out[4], uint32_t uptime_ms)
{
    put_u32(out, uptime_ms);
}

int rdk_unpack_heartbeat(const uint8_t *payload, uint8_t len, uint32_t *uptime_ms)
{
    if ((payload == 0) || (uptime_ms == 0) || (len != 4u)) {
        return -1;
    }
    *uptime_ms = get_u32(payload);
    return 0;
}

void rdk_pack_cmd_vel(uint8_t out[6], const rdk_cmd_vel_t *cmd)
{
    put_i16(&out[0], cmd->vx_mm_s);
    put_i16(&out[2], cmd->vy_mm_s);
    put_i16(&out[4], cmd->wz_mrad_s);
}

int rdk_unpack_cmd_vel(const uint8_t *payload, uint8_t len, rdk_cmd_vel_t *cmd)
{
    if ((payload == 0) || (cmd == 0) || (len != 6u)) {
        return -1;
    }
    cmd->vx_mm_s = get_i16(&payload[0]);
    cmd->vy_mm_s = get_i16(&payload[2]);
    cmd->wz_mrad_s = get_i16(&payload[4]);
    return 0;
}

static float get_f32_le(const uint8_t *in)
{
    /* Little-endian IEEE-754 float; STM32F4 is little-endian so a memcpy is safe. */
    float v;
    memcpy(&v, in, sizeof(v));
    return v;
}

int rdk_unpack_set_pid(const uint8_t *payload, uint8_t len, rdk_pid_gains_t *gains)
{
    if ((payload == 0) || (gains == 0) || (len != 17u)) {
        return -1;
    }
    gains->wheel = payload[0];
    gains->kp = get_f32_le(&payload[1]);
    gains->ki = get_f32_le(&payload[5]);
    gains->kd = get_f32_le(&payload[9]);
    gains->ff = get_f32_le(&payload[13]);
    return 0;
}

void rdk_pack_status(uint8_t out[8], const rdk_status_t *status)
{
    out[0] = status->mode;
    out[1] = status->estop;
    put_u16(&out[2], status->fault_code);
    put_u16(&out[4], status->battery_mv);
    out[6] = status->last_cmd_seq;
    out[7] = status->comm_state;
}

void rdk_pack_ack(uint8_t out[3], const rdk_ack_t *ack)
{
    out[0] = ack->ack_type;
    out[1] = ack->ack_seq;
    out[2] = ack->result;
}

void rdk_pack_odom(uint8_t out[8], int16_t lf, int16_t rf, int16_t lr, int16_t rr)
{
    put_i16(&out[0], lf);
    put_i16(&out[2], rf);
    put_i16(&out[4], lr);
    put_i16(&out[6], rr);
}

void rdk_pack_fault(uint8_t out[4], uint16_t fault_code, uint16_t detail)
{
    put_u16(&out[0], fault_code);
    put_u16(&out[2], detail);
}
