/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file    usbd_cdc_if.h
  * @brief   CDC VCP interface for the STM32F411 chassis link. Hand-added.
  ******************************************************************************
  */
/* USER CODE END Header */

#ifndef __USBD_CDC_IF_H__
#define __USBD_CDC_IF_H__

#ifdef __cplusplus
extern "C" {
#endif

#include "usbd_cdc.h"

/* FS endpoint packet size for CDC data. */
#define APP_RX_DATA_SIZE  64
#define APP_TX_DATA_SIZE  256

extern USBD_CDC_ItfTypeDef USBD_Interface_fops_FS;

uint8_t CDC_Transmit_FS(uint8_t *Buf, uint16_t Len);

/* Implemented in main.c: feed received CDC bytes into the rdk protocol parser.
   Weak default in usbd_cdc_if.c does nothing, so the library links standalone. */
void rdk_comm_on_rx_bytes(const uint8_t *data, uint32_t len);

#ifdef __cplusplus
}
#endif

#endif /* __USBD_CDC_IF_H__ */
