/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file    usbd_conf.h
  * @brief   USB Device configuration for STM32F411 OTG_FS (CDC VCP).
  *          Hand-added (not CubeMX) to keep the existing hand-edited main.c
  *          intact. Targets USB_OTG_FS, VBUS sensing disabled, static alloc.
  ******************************************************************************
  */
/* USER CODE END Header */

#ifndef __USBD_CONF__H__
#define __USBD_CONF__H__

#ifdef __cplusplus
extern "C" {
#endif

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "stm32f4xx.h"
#include "stm32f4xx_hal.h"

/* Common config */
#define USBD_MAX_NUM_INTERFACES               1U
#define USBD_MAX_NUM_CONFIGURATION            1U
#define USBD_MAX_STR_DESC_SIZ                 512U
#define USBD_DEBUG_LEVEL                      0U
#define USBD_LPM_ENABLED                      0U
#define USBD_SELF_POWERED                     1U
#define DEVICE_FS                             0

/* Memory management: static allocation (no heap dependency) */
void *USBD_static_malloc(uint32_t size);
void USBD_static_free(void *p);

/* The CDC class data is the largest single allocation; size the static pool to it. */
#define USBD_malloc         (void *)USBD_static_malloc
#define USBD_free           USBD_static_free
#define USBD_memset         memset
#define USBD_memcpy         memcpy
#define USBD_Delay          HAL_Delay

/* DEBUG macros */
#if (USBD_DEBUG_LEVEL > 0U)
#define USBD_UsrLog(...)    do { printf(__VA_ARGS__); printf("\n"); } while (0)
#else
#define USBD_UsrLog(...) do {} while (0)
#endif

#if (USBD_DEBUG_LEVEL > 1U)
#define USBD_ErrLog(...)    do { printf("ERROR: "); printf(__VA_ARGS__); printf("\n"); } while (0)
#else
#define USBD_ErrLog(...) do {} while (0)
#endif

#if (USBD_DEBUG_LEVEL > 2U)
#define USBD_DbgLog(...)    do { printf("DEBUG : "); printf(__VA_ARGS__); printf("\n"); } while (0)
#else
#define USBD_DbgLog(...) do {} while (0)
#endif

#ifdef __cplusplus
}
#endif

#endif /* __USBD_CONF__H__ */
